import asyncio
from typing import List, Any
import os
import spacy
import json
import re
from ..prompts import PromptGetter
from app.core.llms import get_llm_response, TokenUsage
from app.logger import get_logger
# from app.databases.vector_operations import VectorStore
from app.databases.vector.operations import VectorStore


logger = get_logger()


NLP_MODELS = {}


def build_nlp_for_dataset(dbname: str):
    """Load spacy model and add dataset-specific patterns once."""
    if dbname in NLP_MODELS:
        return NLP_MODELS[dbname]

    nlp = spacy.load("en_core_web_sm")

    print(os.listdir("business_data/cx_customer_experience"))

    # Load dataset-specific patterns
    base_business_context_path = os.path.join(
        "business_data", dbname, "business_context.json"
    )
    with open(base_business_context_path, "r") as f:
        json_data = json.load(f)

    unique_column_values_mappings = json_data["unique_value_col_table_mappings"]
    unique_values = set()
    for v in unique_column_values_mappings.values():
        for i in v:
            unique_values.update(i["unique_value"])

    patterns = []
    for p in unique_values:
        if not p or not p.strip():
            continue  # skip empty/blank strings
        patterns.append({"label": "CUSTOM", "pattern": p})
        # patterns.append({"label": "CUSTOM", "pattern": [{"LOWER": i} for i in p.lower().split()]})
        # Token-based pattern
        tokens = [{"LOWER": i} for i in p.lower().split() if i.strip()]
        if tokens:  # avoid zero-token patterns
            patterns.append({"label": "CUSTOM", "pattern": tokens})

            # if len(tokens) > 1:#new
            #     for t in tokens:
            #         token_text = t["LOWER"]
            #         if len(token_text) > 3:  # only keep tokens longer than 3 chars
            #             patterns.append({"label": "CUSTOM", "pattern": [t]})

    # Add entity ruler only once
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    if patterns:  # avoid ValueError if empty
        ruler.add_patterns(patterns)
    # ruler.add_patterns(patterns)

    NLP_MODELS[dbname] = nlp
    return nlp


class Text2SQL:
    def __init__(
        self,
        dbname: str,
        vector_client: VectorStore,
        llm,
        llm_name: str,
        question: str,
        filters: str,
        relevant_questions: list = [],
    ):
        self.dbname = dbname
        self.llm = llm
        self.llm_name = llm_name
        self.question = question
        self.vector_client = vector_client
        self.token_usage: TokenUsage = TokenUsage()
        self.prompt_getter = PromptGetter(dbname)
        self.last_relevant_questions = relevant_questions
        self.data_filters = filters
        self.sys_prompt: None | str = None



        schema_text_file_path = f"app/core/schema_strings/{self.dbname}.txt"
        with open(schema_text_file_path, "r", encoding="UTF-8") as f:
            self.schema_str = f.read()

    async def get_positive_examples(self, num_examples: int = 5):
        exs = await self.vector_client._query_data(
            query_filters={"context_type": "sample_sql_query", "is_positive_example": True}, 
            user_query=self.question, 
            n_results=num_examples
        )
        examples_list = []
        for ex in exs:
            payload = ex["payload"]
            ex = f"<example>User Input: {payload['question']}\nFilters: {payload['filters']}\nResponse: {payload['sql_query']}</example>"
            examples_list.append(ex)
        return "\n\n".join(examples_list)

    async def get_negative_examples(self):
        # question = self.question+"\n"+self.data_filters
        exs = await self.vector_client._query_data(
            query_filters={"context_type": "sample_sql_query", "is_positive_example": False}, 
            user_query=self.question, 
            n_results=2
        )
        examples_list = []
        for ex in exs:
            payload = ex["payload"]
            d = {
                "status": "awaiting_human_input",
                "response": payload["sql_query"],
            }
            ex = f"User Input: {payload['question']}\nFilters: {payload['filters']}\n Response: {d}"
            examples_list.append(ex)
        prefix = "\n\n" if examples_list else ""
        return prefix + "\n\n".join(
            examples_list
        )  # converting the examples to string and returning

    def extract_nlp_candidates(self):
        nlp = build_nlp_for_dataset(self.dbname)  # gets cached model

        candidates = re.findall(r"'([^']+)'|\"([^\"]+)\"", self.question)
        candidates_base = [c[0] or c[1] for c in candidates]

        doc = nlp(self.question)  # <-- this is CPU-bound, not async
        ents = [
            ent.text
            for ent in doc.ents
            if ent.label_ in {"ORG", "GPE", "PERSON", "PRODUCT", "CUSTOM"}
        ]
        noun_chunks = [
            chunk.text for chunk in doc.noun_chunks if len(chunk.text.split()) > 1
        ]

        candidates_nlp = list(set(ents + noun_chunks))
        print('candidates_nlp',candidates_nlp)
        return list(set(candidates_base + candidates_nlp))

    async def get_column_unique_mappings(self, threshold: float = 0.9):
        candidates = self.extract_nlp_candidates()
        matched_blocks = []
        tasks = []
        for cand in candidates:
            task = asyncio.create_task(
                self.vector_client._query_data(
                    query_filters={"context_type": "column_unique_value"},
                    user_query=cand,
                    n_results=5
                )
            )
            tasks.append(task)
        results = await asyncio.gather(*tasks)

        for res, c in zip(results, candidates):
            top = res[0]
            val = top["payload"].get("unique_value")
            col = top["payload"].get("col_name", "unknown_column")

            if top["score"] >= threshold:
                block = f"- '{c}' best matches {col} = '{val}' (score={top['score']:.2f})"
            elif top["score"] >= 0.6:
                block = f"- '{c}' ? possible matches:"
                for r in res:
                    if r["score"] >= 0.6:
                        v = r["payload"].get("unique_value")
                        c = r["payload"].get("col_name", "unknown_column")
                        block += f"\n   * {c} = '{v}' (score={r['score']:.2f})"
            else:
                block = None
            if block:
                matched_blocks.append(block)
        if not candidates:
            return ""
        return "\n".join(matched_blocks) if matched_blocks else ""

    def get_chat_history(self, last_transactions: List[Any]) -> list:
        if len(last_transactions) == 0:
            return []
        chat_history_list = []
        for lt in last_transactions:
            chat_history_list.extend([
                {
                    "role": "user",
                    "content": lt.user_query
                },
                {
                    "role": "assistant",
                    "content": lt.raw_response
                }
            ])
        return chat_history_list

    async def sql_query_generator(self, chat_history: list):
        positive_examples = await self.get_positive_examples()
        candidate_mappings_from_user_question = await self.get_column_unique_mappings()

        text2sql_sys_prompt = self.prompt_getter.get_prompt("text2sql_sys_prompt")
        
        self.sys_prompt = text2sql_sys_prompt.format(
            dialect="mssql",
            schema=self.schema_str,
            matched_values=candidate_mappings_from_user_question,
            examples=positive_examples,
            data_filters=self.data_filters
        )
        
        messages = [{"role": "system", "content": self.sys_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": self.question})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        print("results.........", results)

        print("############ SYSTEM PROMPT ################")
        print('sys prompt........',self.sys_prompt)

        return results
    

    async def sql_query_generator_basic(self, chat_history: list = []):
        text2sql_sys_prompt = self.prompt_getter.get_prompt("text2sql_sys_prompt")
        
        self.sys_prompt = text2sql_sys_prompt.format(
            dialect="mssql",
            schema=self.schema_str,
            matched_values=None,
            examples=None,
            data_filters=None
        )
        
        messages = [{"role": "system", "content": self.sys_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": self.question})

        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage = token_usage
        return results

        
    async def correct_sql_query(self, chat_history: list):
        logger.warning("Initial SQL resulted din error. Regenerating SQL")
        messages = [{"role": "system", "content": self.sys_prompt}]
        messages.extend(chat_history)
        results, token_usage = await get_llm_response(self.llm, self.llm_name, messages)
        self.token_usage.input_tokens = token_usage.input_tokens
        self.token_usage.output_tokens = token_usage.output_tokens
        self.token_usage.cached_tokens = token_usage.cached_tokens    
        return results


#
# if __name__ == "__main__":
#     t = Text2SQL("abc", "abc")
#     user_query = "ratings across years for UK in 2023"
#     print(t.query_generator(user_query))
