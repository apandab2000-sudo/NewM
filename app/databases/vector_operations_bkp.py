import pandas as pd
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    Distance,
)
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import uuid

encoder = "abc"# SentenceTransformer(
#     "sentence-transformers/all-MiniLM-L6-v2", 
#     device="cpu"
# )
print("MODEL LEADED")


class VectorStore:
    def __init__(self, client: AsyncQdrantClient):
        self.collection_name = None
        self.client = client

    async def list_collections(self):
        all_collections = await self.client.get_collections()
        return all_collections

    async def ensure_collection(
        self,
        collection_name: str,
        similarity_metric: str = "cosine",
        vector_dimensions: int = 384,
    ):
        if similarity_metric == "cosine":
            distance_metric = Distance.COSINE
        else:
            distance_metric = Distance.COSINE
        self.collection_name = collection_name
        collection_exists = await self.client.collection_exists(self.collection_name)
        if not collection_exists:
            await self.client.create_collection(
                self.collection_name,
                # vectors_config=VectorParams(
                #     size=vector_dimensions, distance=distance_metric
                # ),
                vectors_config=VectorParams(
                    size=vector_dimensions, 
                    distance=distance_metric
                )
            )
            status = "New Collection Created"
        else:
            status = "Collection Already Exists"
        collection_details = await self.client.get_collection(self.collection_name)
        return collection_details, status

    @staticmethod
    def embed_texts(texts: List[str]) -> List[List[float]]:
        return encoder.encode(texts).tolist()
    
    @staticmethod
    def embed_text(text: str) -> List[List[float]]:
        return encoder.encode(text).tolist()
    
    async def upsert_data(self, data_points: List[Dict[str, Any]]):
        documents = [q_dict["question"].strip() for q_dict in data_points]
        embeddings = self.embed_texts(documents)

        print(len(embeddings))
        print(len(embeddings[0]))
        print(pd.DataFrame(data_points))

        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()), 
                        vector=j, 
                        payload=k
                    )
                    for j, k in zip(embeddings, data_points) if len(k["question"])>=2
                ]
            )
            print("DATA STORED SUCCESSFULLY")
            return True
        except Exception as e:
            print(str(e))
            print("DATA NOT STORED PROPERLY")
            return False

    async def upsert_data_column_context(self, data_points: List[Dict[str, Any]]):
        
        documents = [q_dict["unique_value"].strip() for q_dict in data_points]
        embeddings = self.embed_texts(documents)
        
        print(len(embeddings))
        print(len(embeddings[0]))
        print(pd.DataFrame(data_points).head())
        
        data_points_updated = []
        for i in data_points:
            i["context_type"] = "column_unique_value"
            data_points_updated.append(i)
        
        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()), 
                        vector=j, 
                        payload=k
                    )
                    for j, k in zip(embeddings, data_points_updated) if len(k["unique_value"])>=2
                ],
            )
            print("COLUMN UNIQUE VALUE DATA STORED SUCCESSFULLY")
            return True
        except Exception as e:
            print(str(e))
            print("COLUMN UNIQUE VALUE DATA NOT STORED PROPERLY")
            return False

    # async def upsert_data(self, data_points: List[Dict[str, Any]]):
    #     documents = [
    #         q_dict["question"].strip()
    #         for q_dict in data_points
    #     ]

    #     embeddings = self.embed_texts(documents)
    #     print(len(embeddings))
    #     print(len(embeddings[0]))
    #     print(pd.DataFrame(data_points))
    #     try:
    #         await self.client.upsert(
    #             collection_name=self.collection_name,
    #             points=[
    #                 PointStruct(id=str(uuid.uuid4()), vector={"text": j}, payload=k)
    #                 for i, j, k in zip(range(len(data_points)), embeddings, data_points)
    #                 if len(k["question"])>=2
    #             ],
    #         )
    #         print("DATA STORED SUCCESSFULLY")
    #         return True
    #     except Exception as e:
    #         print(str(e))
    #         print("DATA NOT STORED PROPERLY")
    #         return False

    # async def upsert_data_column_context(self, data_points: List[Dict[str, Any]]):
    #     documents = [q_dict["unique_value"].strip() for q_dict in data_points]
    #     embeddings = self.embed_texts(documents)
    #     print(len(embeddings))
    #     print(len(embeddings[0]))
    #     print(pd.DataFrame(data_points).head())
    #     data_points_updated = []
    #     for i in data_points:
    #         i["context_type"] = "column_unique_value"
    #         data_points_updated.append(i)
    #     try:
    #         await self.client.upsert(
    #             collection_name=self.collection_name,
    #             points=[
    #                 PointStruct(id=str(uuid.uuid4()), vector={"text": j}, payload=k)
    #                 for i, j, k in zip(
    #                     range(len(data_points_updated)), embeddings, data_points_updated
    #                 ) if len(k["unique_value"])>=2
    #             ],
    #         )
    #         print("COLUMN UNIQUE VALUE DATA STORED SUCCESSFULLY")
    #         return True
    #     except Exception as e:

    #         print(str(e))
    #         print("COLUMN UNIQUE VALUE DATA NOT STORED PROPERLY")
    #         return False

    async def query_data(
        self,
        user_query: str,
        query_filter: str = "sample_sql_query",
        positive_examples: bool = True,
        n_results: int = 5,
    ):

        embedding = self.embed_text(user_query)

        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=embedding,
            limit=n_results,
            with_payload=True,
            query_filter=Filter(
                must=[
                    FieldCondition(key="context_type", match=MatchValue(value=query_filter)),
                    FieldCondition(key="is_positive_example", match=MatchValue(value=positive_examples)),
                ]
            ),
        )

        for result in results.points:
            print(result.payload, "Score:", result.score)

        return results.points

    # async def query_data_for_examples(self, user_query, query_filter: str = "business_context",n_results: int = 5):
    #     results = await self.client.query_points(
    #         collection_name=self.collection_name,
    #         query=self.embed_texts([user_query])[0],
    #         limit=n_results,
    #         with_payload=True,
    #         query_filter=Filter(must=FieldCondition(key="context_type", match=MatchValue(value=query_filter)))
    #     )
    #     # examples = [{"query": i.payload["question"], "input": i.payload["sql_query"]} for i in results.points]
    #     return results

    # async def query_data_for_column_uniques_bkp1(
    #     self,
    #     candidate: str,
    #     query_filter: str = "column_unique_value",
    #     n_results: int = 3,
    # ):
    #     results = await self.client.query_points(
    #     collection_name=self.collection_name,
    #     query_vector={"text": self.embed_texts([user_query])[0]},
    #     limit=n_results,
    #     with_payload=True,
    #     query_filter=Filter(
    #                 must=[
    #                     FieldCondition(key="context_type", match=MatchValue(value=query_filter)),
    #                     FieldCondition(key="is_positive_example", match=MatchValue(value=positive_examples)),
    #                 ]
    #             ),
    #         )

    #     for result in results.points:
    #         print(result.payload, "Score:", result.score)
    #     return results.points
    async def query_data_for_column_uniques(
        self,
        candidate: str,
        query_filter: str = "column_unique_value",
        n_results: int = 3,
    ):
        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=self.embed_text(candidate),
            limit=n_results,
            with_payload=True,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="context_type", match=MatchValue(value=query_filter)
                    )
                ]
            ),
        )

        for result in results.points:
            print(result.payload, "Score:", result.score)

        return results.points



# async def add_data(data):
#     store = VectorStore("abcd")
#     await store.ensure_collection()
#     # await store.upsert_data(data)
#     r = await store.query_data_for_examples("milvus is too good")
#     print(r)


# if __name__ == "__main__":
#     data_to_add = [
#         {
#             "question": "I too like milvus",
#             "sql_query": "asjdhasjdhjsad askjdaksd zadas sa",
#             "context_type": "business_context"
#         },
#         {
#             "question": "milvus is good",
#             "sql_query": "asjdhasjd asda asd asdsdff ks dkas dhjsad askjdaksd sa",
#             "context_type": "business_context"
#         },
#         {
#             "question": "milvus is good",
#             "sql_query": "asjdhasjd asda asd asdsdff ks dkas dhjsad askjdaksd sa",
#             "context_type": "business_kpi"
#         }
#     ]
#
#     asyncio.run(add_data(data_to_add))
