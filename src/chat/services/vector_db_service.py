# -*- coding: utf-8 -*-

import logging
from typing import List, Dict, Any

import chromadb
from chromadb.types import Collection

from src.chat.config import chat_config as config

log = logging.getLogger(__name__)

class VectorDBService:
    """
    封装与 ChromaDB 向量数据库交互的服务。
    """
    def __init__(self):
        try:
            # 初始化持久化客户端
            self.client = chromadb.PersistentClient(path=config.VECTOR_DB_PATH)
            
            # 获取或创建集合
            self.collection: Collection = self.client.get_or_create_collection(
                name=config.VECTOR_DB_COLLECTION_NAME
            )
            log.info(f"成功连接到 ChromaDB 并加载集合: '{config.VECTOR_DB_COLLECTION_NAME}'")
        except Exception as e:
            log.error(f"初始化 ChromaDB 服务失败: {e}", exc_info=True)
            self.client = None
            self.collection = None

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.client is not None and self.collection is not None

    def recreate_collection(self):
        """
        删除并重新创建集合，以确保数据完全同步。
        """
        if not self.client:
            log.error("VectorDB 客户端未初始化，无法重新创建集合。")
            return
        
        try:
            log.info(f"正在删除旧的集合: '{config.VECTOR_DB_COLLECTION_NAME}'...")
            self.client.delete_collection(name=config.VECTOR_DB_COLLECTION_NAME)
            log.info("旧集合已删除。")
        except Exception as e:
            # 即使集合不存在，尝试删除也可能引发异常，但我们可以忽略它
            log.warning(f"删除集合时出现错误 (可能集合不存在，可以忽略): {e}")

        try:
            log.info(f"正在创建新的集合: '{config.VECTOR_DB_COLLECTION_NAME}'...")
            self.collection = self.client.create_collection(
                name=config.VECTOR_DB_COLLECTION_NAME
            )
            log.info("新集合已成功创建。")
        except Exception as e:
            log.error(f"创建新集合时出错: {e}", exc_info=True)
            # 如果创建失败，将 collection 设为 None 以反映状态
            self.collection = None
 
    def add_documents(self, ids: List[str], documents: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        """
        向集合中添加或更新文档及其元数据。

        Args:
            ids: 文档的唯一ID列表。
            documents: 文档内容（文本）列表。
            embeddings: 与文档对应的嵌入向量列表。
            metadatas: 与文档对应的元数据字典列表。
        """
        if not self.is_available():
            log.error("VectorDB 服务不可用，无法添加文档。")
            return

        try:
            # 使用 upsert 来添加新文档或更新现有文档，现在包含元数据
            self.collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
            log.info(f"成功向集合 '{self.collection.name}' 中添加/更新了 {len(ids)} 个文档。")
        except Exception as e:
            log.error(f"向 ChromaDB 添加文档时出错: {e}", exc_info=True)

    def search(self, query_embedding: List[float], n_results: int = 3, max_distance: float = 0.75) -> List[Dict[str, Any]]:
        """
        在集合中执行语义搜索，并根据距离阈值过滤结果。

        Args:
            query_embedding: 用于查询的嵌入向量。
            n_results: 要返回的最相似结果的数量。
            max_distance: 结果必须满足的最大距离。超过此距离的结果将被丢弃。

        Returns:
            一个包含搜索结果的字典列表，每个字典包含 'id', 'content', 'distance', 和 'metadata'。
        """
        if not self.is_available():
            log.error("VectorDB 服务不可用，无法执行搜索。")
            return []

        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                include=["documents", "distances", "metadatas"] # 明确请求返回元数据
            )
            
            # 解包并格式化结果
            unfiltered_results = []
            if results and results['ids'] and results['ids'][0]:
                ids = results['ids'][0]
                documents = results['documents'][0]
                distances = results['distances'][0]
                metadatas = results['metadatas'][0]
                
                for i in range(len(ids)):
                    unfiltered_results.append({
                        "id": ids[i],
                        "content": documents[i],
                        "distance": distances[i],
                        "metadata": metadatas[i]
                    })
            
            # 根据 max_distance 过滤结果
            filtered_results = [res for res in unfiltered_results if res['distance'] <= max_distance]
            
            log.info(f"原始召回 {len(unfiltered_results)} 个结果, 距离阈值过滤后剩余 {len(filtered_results)} 个。")
            
            return filtered_results
        except Exception as e:
            log.error(f"在 ChromaDB 中搜索时出错: {e}", exc_info=True)
            return []

# 全局实例
vector_db_service = VectorDBService()