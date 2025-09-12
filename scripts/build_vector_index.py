# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import logging
import re
import sqlite3

import yaml
from dotenv import load_dotenv

# --- 配置项目根路径 ---
# 这使得脚本可以从任何位置运行，同时能够正确导入 src 目录下的模块
# 获取当前脚本文件的绝对路径
current_script_path = os.path.abspath(__file__)
# 获取脚本所在目录的路径 (scripts)
script_dir = os.path.dirname(current_script_path)
# 获取项目根目录的路径 (Odysseia-Guidance)
project_root = os.path.dirname(script_dir)
# 将项目根目录添加到 sys.path
sys.path.insert(0, project_root)
# --- 路径配置结束 ---

# --- 环境变量加载 ---
# 必须在导入任何服务之前加载环境变量
env_path = os.path.join(project_root, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
    print(".env 文件已加载。") # 使用 print 以便在日志配置前就能看到
else:
    print(".env 文件未找到，请确保 GEMINI_API_KEYS 已在环境中设置。")
# --- 环境变量加载结束 ---


# 现在可以安全地导入项目模块
from src.services.gemini_service import gemini_service
from src.services.vector_db_service import vector_db_service

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# 定义知识库文件路径
KNOWLEDGE_FILE_PATH = os.path.join(project_root, 'src', 'world_book', 'data', 'knowledge.yml')

# 定义世界之书数据库路径
WORLD_BOOK_DB_PATH = os.path.join(project_root, 'src', 'world_book', 'data', 'world_book.sqlite3')

def create_text_chunks(text: str, max_chars: int = 1000) -> list[str]:
    """
    根据句子边界将长文本分割成更小的块。
    该函数会尝试创建尽可能大但不超过 max_chars 的文本块。
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    
    # 如果整个文本已经足够小，将其作为单个块返回。
    if len(text) <= max_chars:
        return [text]

    # 按句子分割文本。正则表达式包含中英文常见的句子结束符以及换行符。
    sentences = re.split(r'(?<=[。？！.!?\n])\s*', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return []

    final_chunks = []
    current_chunk = ""
    for sentence in sentences:
        # 如果单个句子超过 max_chars，它将自成一块。
        # 这是一种备用策略，理想情况下应通过格式良好的源数据来避免。
        if len(sentence) > max_chars:
            if current_chunk:
                final_chunks.append(current_chunk)
            final_chunks.append(sentence)
            current_chunk = ""
            continue

        # 如果添加下一个句子会超过 max_chars 限制，
        # 则完成当前块并开始一个新块。
        if len(current_chunk) + len(sentence) + 1 > max_chars: # +1 是为了空格
            final_chunks.append(current_chunk)
            current_chunk = sentence
        else:
            # 否则，将句子添加到当前块。
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
    
    # 将最后一个剩余的块添加到列表中。
    if current_chunk:
        final_chunks.append(current_chunk)
        
    return final_chunks


# --- 文本构建器 ---

def _format_content_dict(content_dict: dict) -> str:
    """将 content 字典格式化为多行的 ' - key: value' 字符串列表。"""
    if not isinstance(content_dict, dict):
        return [f" - {content_dict}"]
    return [f" - {key}: {value}" for key, value in content_dict.items()]

def _build_text_community_member(entry: dict) -> str:
    """为“社区成员”类别构建结构化文本。"""
    text_parts = ["类别: 社区成员"]
    
    nicknames = entry.get('discord_nickname', [])
    if nicknames:
        text_parts.append("昵称:")
        text_parts.extend([f" - {name}" for name in nicknames])
        
    content_lines = _format_content_dict(entry.get('content', {}))
    if content_lines:
        text_parts.append("人物信息:")
        text_parts.extend(content_lines)
        
    return "\n".join(text_parts)

def _build_text_generic(entry: dict, category_name: str) -> str:
    """为“社区信息”、“文化”、“事件”等通用类别构建结构化文本。"""
    name = entry.get('name', entry.get('id', ''))
    text_parts = [f"类别: {category_name}", f"名称: {name}"]
    
    aliases = entry.get('aliases', [])
    if aliases:
        text_parts.append("别名:")
        text_parts.extend([f" - {alias}" for alias in aliases])
        
    content_lines = _format_content_dict(entry.get('content', {}))
    if content_lines:
        text_parts.append("描述:")
        text_parts.extend(content_lines)
        
    return "\n".join(text_parts)

def _build_text_slang(entry: dict) -> str:
    """为“俚语”类别构建结构化文本。"""
    name = entry.get('name', entry.get('id', ''))
    text_parts = [f"类别: 俚语", f"名称: {name}"]
    
    aliases = entry.get('aliases', [])
    if aliases:
        text_parts.append("也称作:")
        text_parts.extend([f" - {alias}" for alias in aliases])
        
    refers_to = entry.get('refers_to', [])
    if refers_to:
        text_parts.append("通常指代:")
        text_parts.extend([f" - {item}" for item in refers_to])
        
    content_lines = _format_content_dict(entry.get('content', {}))
    if content_lines:
        text_parts.append("具体解释:")
        text_parts.extend(content_lines)
        
    return "\n".join(text_parts)

def build_document_text(entry: dict) -> str:
    """
    根据条目的类别，调用相应的函数来构建用于嵌入的文本文档。
    这是一个总调度函数。
    """
    category = entry.get("metadata", {}).get("category")

    # 将类别映射到相应的构建函数
    builders = {
        "社区成员": _build_text_community_member,
        "社区信息": lambda e: _build_text_generic(e, "社区信息"),
        "社区文化": lambda e: _build_text_generic(e, "社区文化"),
        "社区大事件": lambda e: _build_text_generic(e, "社区大事件"),
        "俚语": _build_text_slang,
    }

    builder_func = builders.get(category)

    if builder_func:
        return builder_func(entry)
    else:
        # 如果没有找到特定的构建器，则记录警告并使用默认的 content 转换
        log.warning(f"条目 '{entry.get('id')}' 的类别 '{category}' 没有找到特定的文本构建器，将使用默认内容。")
        content = entry.get("content", "")
        return str(content) if isinstance(content, dict) else content


def load_general_knowledge_from_db() -> list:
    """
    从 world_book.sqlite3 数据库的 general_knowledge 表中加载所有条目。
    返回一个字典列表，格式与 knowledge.yml 中的条目相似。
    """
    db_entries = []
    try:
        with sqlite3.connect(WORLD_BOOK_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, name, content_text, category_name, contributor_id, created_at FROM general_knowledge")
            rows = cursor.fetchall()
            
            for row in rows:
                entry_id, title, name, content_text, category_name, contributor_id, created_at = row
                # 构造与 knowledge.yml 条目相似的结构
                entry = {
                    'id': f"db_{entry_id}",  # 使用前缀避免与YAML中的ID冲突
                    'title': title or name,  # 如果title为空，使用name
                    'name': name,
                    'content': content_text,
                    'metadata': {
                        'category': category_name or "通用知识",  # 如果category_name为空，使用默认值
                        'source': 'database',
                        'contributor_id': contributor_id,
                        'created_at': created_at
                    }
                }
                db_entries.append(entry)
                
        log.info(f"成功从数据库加载了 {len(db_entries)} 个通用知识条目。")
    except sqlite3.Error as e:
        log.error(f"从数据库读取通用知识条目时出错: {e}")
    except Exception as e:
        log.error(f"处理数据库条目时发生未知错误: {e}", exc_info=True)
        
    return db_entries


async def main():
    """
    主函数，用于构建或更新向量索引。
    """
    log.info("--- 开始构建向量数据库索引 ---")

    # 1. 检查服务可用性
    if not gemini_service.is_available():
        log.error("GeminiService 不可用，无法生成嵌入。请检查您的 API 密钥配置。")
        return
    if not vector_db_service.is_available():
        log.error("VectorDBService 不可用，无法存储文档。请检查 ChromaDB 配置。")
        return
    
    log.info("Gemini 和 VectorDB 服务均已成功初始化。")

    # 2. 清理并重建集合
    # 这是关键一步，确保每次都从一个干净的状态开始，防止旧数据残留。
    log.info("正在重建向量数据库集合以确保数据同步...")
    vector_db_service.recreate_collection()
    if not vector_db_service.is_available():
        log.error("重建集合后，VectorDBService 变为不可用。脚本终止。")
        return
    log.info("集合重建成功。")
 
    # 3. 读取 YAML 知识库文件
    try:
        with open(KNOWLEDGE_FILE_PATH, 'r', encoding='utf-8') as f:
            # 使用 safe_load 来处理单文档 YAML (现在是一个对象列表)
            yaml_knowledge_entries = yaml.safe_load(f)
        log.info(f"成功从 '{KNOWLEDGE_FILE_PATH}' 加载了 {len(yaml_knowledge_entries)} 个知识条目。")
    except FileNotFoundError:
        log.error(f"知识库文件未找到: '{KNOWLEDGE_FILE_PATH}'")
        return
    except Exception as e:
        log.error(f"读取或解析 YAML 文件时出错: {e}", exc_info=True)
        return

    # 4. 从数据库加载通用知识条目
    db_knowledge_entries = load_general_knowledge_from_db()
    
    # 5. 合并来自 YAML 和数据库的知识条目
    knowledge_entries = yaml_knowledge_entries + db_knowledge_entries
    log.info(f"合并后总共有 {len(knowledge_entries)} 个知识条目。")

    # 4. 准备要添加到数据库的数据
    ids_to_add = []
    documents_to_add = []
    embeddings_to_add = []
    metadatas_to_add = [] # 新增：用于存储元数据

    total_entries_processed = 0
    total_chunks_generated = 0

    log.info("开始为每个知识条目生成嵌入向量...")
    for i, entry in enumerate(knowledge_entries):
        # 检查基本字段和元数据字段
        if not isinstance(entry, dict) or 'id' not in entry or 'content' not in entry or 'metadata' not in entry:
            log.warning(f"跳过格式不正确或缺少元数据的条目 #{i+1}: {entry}")
            continue

        original_id = str(entry['id'])
        # entry_content = str(entry['content']) # 旧方法：直接使用 content
        entry_metadata = entry['metadata']
        # --- 新增：获取标题 ---
        entry_title = entry.get('title')
        if not entry_title:
            log.warning(f"条目 id='{original_id}' 缺少 'title' 字段，将使用 id 作为备用标题。")
            entry_title = original_id
        # --- 结束 ---

        log.info(f"[{i+1}/{len(knowledge_entries)}] 开始处理条目: id='{original_id}', title='{entry_title}'")

        # --- 修正：使用 build_document_text 来构建结构化文本 ---
        document_text = build_document_text(entry)
        log.info(f"  -> 构建的文档文本 (前100字符): \"{document_text[:100].replace(chr(10), ' ')}...\"")

        # --- 使用新的分块函数 ---
        chunks = create_text_chunks(document_text, max_chars=1000)
        
        if not chunks:
            log.warning(f"  -> 条目 id='{original_id}' 的内容无法分块，跳过。")
            continue

        log.info(f"  -> 文本被分割成 {len(chunks)} 个块。")
        total_chunks_generated += len(chunks)

        for chunk_index, chunk_content in enumerate(chunks):
            # 为每个块创建唯一的ID
            chunk_id = f"{original_id}:{chunk_index}"
            
            log.info(f"    正在处理块 {chunk_index + 1}/{len(chunks)} (ID: {chunk_id})")

            # --- 使用原生 title 参数生成嵌入 ---
            # log.info(f"      -> 准备嵌入的文本: \"{chunk_content[:80]}...\"") # 日志级别调整为 DEBUG

            # 为文本块生成嵌入向量，并传入标题
            embedding = await gemini_service.generate_embedding(
                text=chunk_content,
                title=entry_title,
                task_type="retrieval_document"
            )

            if embedding:
                ids_to_add.append(chunk_id)
                documents_to_add.append(chunk_content)
                embeddings_to_add.append(embedding)
                metadatas_to_add.append(entry_metadata) # 为每个块关联相同的元数据
                log.info(f"      -> 成功生成嵌入向量。")
            else:
                log.error(f"      -> 未能为 id='{chunk_id}' 生成嵌入向量，将跳过此块。")
        
        total_entries_processed += 1

    # 5. 将数据批量添加到向量数据库
    if ids_to_add:
        log.info(f"准备将 {len(ids_to_add)} 个文档块批量写入向量数据库...")
        try:
            vector_db_service.add_documents(
                ids=ids_to_add,
                documents=documents_to_add,
                embeddings=embeddings_to_add,
                metadatas=metadatas_to_add # 传递元数据
            )
            log.info("文档已成功批量添加到数据库。")
        except Exception as e:
            log.error(f"批量添加文档到数据库时发生错误: {e}", exc_info=True)
    else:
        log.warning("没有成功生成任何嵌入向量，无需更新数据库。")

    log.info("--- 向量数据库索引构建完成 ---")
    log.info(f"处理摘要:")
    log.info(f"  - 总共处理了 {total_entries_processed} 个知识条目。")
    log.info(f"  - 总共生成并存储了 {total_chunks_generated} 个文本块。")


if __name__ == "__main__":
    # 为了在顶层运行 await，我们使用 asyncio.run()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("脚本被用户中断。")
    except Exception as e:
        log.error(f"脚本执行期间发生未捕获的错误: {e}", exc_info=True)