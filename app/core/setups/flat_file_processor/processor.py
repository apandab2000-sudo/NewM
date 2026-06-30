from abc import ABC, abstractmethod
from pathlib import Path
import zipfile
import pandas as pd
from app.logger import get_logger


logger = get_logger(__name__)


def extract_zip_file(zip_path: Path, extract_to: Path) -> bool:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        return True
    except Exception as e:
        logger.error(f"Error extracting zip file: {e}")
        return False


class FlatFileProcessor(ABC):
    @abstractmethod
    async def process_file(self, file_path: Path, final_dir: Path, db_name: str, mode: str):
        ...

    def convert_to_parquet(self, df: pd.DataFrame, destination_path: Path, mode: str) -> bool:
        if mode == "append" and destination_path.exists():
            existing_df = pd.read_parquet(destination_path)
            df = pd.concat([existing_df, df], ignore_index=True)
            logger.debug(f"Appended data to existing Parquet file at {destination_path}")
        elif mode == "replace" and destination_path.exists():
            df.to_parquet(destination_path, index=False)
            logger.debug(f"Replaced existing Parquet file at {destination_path}")
        else:
            df.to_parquet(destination_path, index=False)
            logger.debug(f"Converted CSV to Parquet at {destination_path}")
        return True
    
    def create_final_directory(self, file_path: Path) -> Path:
        final_dir = file_path.parent.parent / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        return final_dir

    def cleanup(self, file_path: Path):  # only keeps the zip file and removes the extracted files after processing
        try:
            for item in file_path.parent.iterdir():
                if item.is_file() and item.suffix.lower() != ".zip":
                    item.unlink()
                    logger.debug(f"Deleted extracted file: {item}")
        except Exception as e:
            logger.error(f"Error during cleanup of extracted files: {e}")
            raise


class CSVProcessor(FlatFileProcessor):
    async def process_file(self, file_path: Path, final_dir: Path, db_name: str, mode: str):
        encodings = ['utf-8', 'latin1', 'iso-8859-1', 'windows-1252']
        df = None

        final_path = final_dir / file_path.name.replace(" ", "_").lower()

        for encoding in encodings:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                logger.debug(f"Successfully read {file_path} with encoding {encoding}")
                self.convert_to_parquet(df, final_path.with_suffix('.parquet'), mode)
                break
            except UnicodeDecodeError as e:
                logger.debug(f"Failed to read {file_path} with encoding {encoding}: {repr(e)}")
                continue
        if df is None:
            logger.error(f"Could not read {file_path} with any encoding")
            raise ValueError(f"Failed to read CSV file with supported encodings: {encodings}")



class ExcelProcessor(FlatFileProcessor):
    def process_file(self, file_path: Path, final_dir: Path, db_name: str, mode: str):

        final_path = final_dir / file_path.name.replace(" ", "_").lower()

        for sheet_name in pd.ExcelFile(file_path).sheet_names:
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                logger.debug(f"Successfully read sheet {sheet_name} from {file_path}")
                destination_path = final_path.with_name(f"{final_path.stem}_{sheet_name}.parquet")
                self.convert_to_parquet(df, destination_path, mode)
            except Exception as e:
                logger.error(f"Error processing sheet {sheet_name} in Excel file {file_path}: {repr(e)}")
                continue

class ParquetProcessor(FlatFileProcessor):
    def process_file(self, file_path: Path, final_dir: Path, db_name: str, mode: str):

        final_path = final_dir / file_path.name.replace(" ", "_").lower()

        try:
            df = pd.read_parquet(final_path)
            logger.debug(f"Successfully read Parquet file {final_path}")
            self.convert_to_parquet(df, final_path.with_suffix('.parquet'), mode)
        except Exception as e:
            logger.error(f"Error processing Parquet file {final_path}: {repr(e)}")
            raise

    
class FlatFileProcessorFactory:
    factory_map = {
        "csv": CSVProcessor(),
        "xls": ExcelProcessor(),
        "xlsx": ExcelProcessor(),
        "parquet": ParquetProcessor()
    }

    @classmethod
    def get_processor(cls, file_extension: str) -> FlatFileProcessor:
        processor = cls.factory_map.get(file_extension.strip('.').lower())
        if not processor:
            logger.error(f"No processor found for file extension: {file_extension}")
            raise ValueError(f"Unsupported file type: {file_extension}")
        logger.debug(f"Processor {processor.__class__.__name__} selected for file extension: {file_extension}")
        return processor


def get_processor_for_file(file_path: Path) -> FlatFileProcessor:
    file_extension = file_path.suffix.lower()
    processor = FlatFileProcessorFactory.get_processor(file_extension)
    return processor


def process_uploaded_file(file_path: Path, db_name: str, mode: str = "new"):
    extract_zip_file(file_path, file_path.parent) # Extract the zip file to the same directory as the uploaded file
    
    unsupported_files = []

    for extracted_file in file_path.parent.iterdir():
        if extracted_file.is_file() and extracted_file.suffix.lower() in [".csv", ".xls", ".xlsx", ".parquet"]:
            processor = get_processor_for_file(extracted_file)
            final_dir = processor.create_final_directory(extracted_file)
            processor.process_file(extracted_file, final_dir, db_name, mode)
        else:
            if extracted_file.suffix.lower() != ".zip":
                unsupported_files.append(extracted_file.name)

    if unsupported_files:
        logger.warning(f"Unsupported files found: {unsupported_files}")

    # Cleanup extracted files after processing
    processor.cleanup(file_path)
    return unsupported_files
