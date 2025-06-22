from langchain.indexes import SQLRecordManager, index
from langchain.docstore.document import Document
from langchain.embeddings.base import Embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List
from langchain_community.document_loaders import PyMuPDFLoader
from uuid import uuid4
from langchain_postgres.vectorstores import PGVector
from langchain_community.document_loaders import WebBaseLoader
import bs4
import os



class RAGIndexer:
    def __init__(
        self,
        connection_string: str,
        embedding_model: Embeddings,
        user_id: str,
        mode: str = "private",
        base_collection: str = "rag_docs",
        use_jsonb: bool = True,
        source_key: str = "source",
        chunk_size: int = 1024,
        chunk_overlap: int =200

    ):
        assert mode in ["private",
                        "public"], "mode must be 'private' or 'public'"

        self.user_id = user_id
        self.mode = mode
        self.connection_string = connection_string
        self.embedding_model = embedding_model
        self.use_jsonb = use_jsonb
        self.source_key = source_key
        self.loader = None
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Namespacing
        self.collection_name = f"{base_collection}_{user_id}" if mode == "private" else f"{base_collection}_public"
        self.namespace = f"{base_collection}_{user_id}" if mode == "private" else f"{base_collection}_public"

        # Record manager
        # self.record_manager = SQLRecordManager(namespace=self.namespace, db_url=connection_string)
        # self.record_manager.create_schema()

        # Vector store
        self.vector_store = PGVector(
            collection_name=self.collection_name,
            embeddings=self.embedding_model,
            connection=connection_string,
            use_jsonb=use_jsonb
        )

        self._doc_filter = lambda x: bool(
            x.page_content and x.page_content.strip())

    def _add_metadata(self, doc: Document, visibility: str = "private") -> Document:
        metadata = doc.metadata or {}
        metadata["owner"] = self.user_id
        metadata["visibility"] = visibility
        doc.metadata = metadata
        return doc

    def _chunking(self, docs: List[Document]) -> List[Document]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        return splitter.split_documents(self.documents)

    def load_pdf(self, path):
        if os.path.exists(path):
            print(f"Loading PDF from {path}")
            self.loader = PyMuPDFLoader(path)
            self.documents = self.loader.load()
        else:
            print("File not found at path", path)
            raise FileNotFoundError(f"File not found at {path}")

    def add_documents(self, isFilter: bool = True, isChunking: bool = True):
        if not self.documents:
            print("Documents are not loaded")
        else:
            if isFilter:
                docs = [doc for doc in self.documents if self._doc_filter(doc)]
            else:
                docs = self.documents

            if isChunking:
                docs = self._chunking(docs)

            ids = [str(uuid4()) for _ in range(len(docs))]
            outIds = self.vector_store.add_documents(docs, ids=ids)
            print("Documents are added successfully")
            return outIds
        
    async def web_base_loader(page_urls):
        loader = WebBaseLoader(
            web_paths=page_urls,
            bs_kwargs={
                "parse_only": bs4.SoupStrainer(class_="theme-doc-markdown markdown"),
            },
            # bs_get_text_kwargs={"separator": " | ", "strip": True}
        )
        documents = []

        async for doc in loader.alazy_load():
            documents.append(doc)

        # assert len(documents) == 1, "No documents loaded from the web page"
        # print("Web page loaded successfully!")
        return documents

    # def add_documents(
    #     self,
    #     docs: List[Document],
    #     visibility: str = "private",
    #     source_id_key: str = "source"
    # ):
    #     enriched_docs = [self._add_metadata(doc, visibility) for doc in docs]
    #     chunked_docs = self._chunking(enriched_docs)

    #     return index(
    #         docs=chunked_docs,
    #         record_manager=self.record_manager,
    #         vector_store=self.vector_store,
    #         cleanup="incremental",
    #         source_id_key=source_id_key
    #     )

    def delete_documents_by_source_ids(self, source_ids: List[str]):
        for source_id in source_ids:
            self.record_manager.delete_keys([source_id])
            self.vector_store.delete(source_id)

    def search(
        self,
        query: str,
        k: int = 5,
        allow_public: bool = True
    ) -> List[Document]:
        results = self.vector_store.similarity_search(query, k=k)

        if allow_public and self.mode != "public":
            public_vs = PGVector.from_existing_index(
                collection_name="rag_docs_public",
                embedding=self.embedding_model,
                connection=self.connection_string,
                use_jsonb=self.use_jsonb
            )
            results.extend(public_vs.similarity_search(query, k=k))

        return results


    def get_vector_store(self):
        return self.vector_store

    def get_record_manager(self):
        return self.record_manager