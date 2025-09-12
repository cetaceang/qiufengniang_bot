#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os

def check_database():
    """检查数据库状态"""
    db_path = 'data/world_book.sqlite3'
    
    print(f"检查数据库: {db_path}")
    print(f"文件存在: {os.path.exists(db_path)}")
    
    if os.path.exists(db_path):
        print(f"文件大小: {os.path.getsize(db_path)} bytes")
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 检查所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            print(f"数据库中的表: {tables}")
            
            # 检查 general_knowledge 表是否存在
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='general_knowledge'")
            general_knowledge_exists = cursor.fetchone()
            print(f"general_knowledge 表存在: {bool(general_knowledge_exists)}")
            
            if general_knowledge_exists:
                # 检查表结构
                cursor.execute("PRAGMA table_info(general_knowledge)")
                columns = cursor.fetchall()
                print("general_knowledge 表结构:")
                for col in columns:
                    print(f"  {col[1]} ({col[2]})")
                
                # 检查数据
                cursor.execute("SELECT COUNT(*) FROM general_knowledge")
                count = cursor.fetchone()[0]
                print(f"general_knowledge 表中的记录数: {count}")
            
            conn.close()
            print("数据库连接成功！")
            
        except Exception as e:
            print(f"数据库连接错误: {e}")
    else:
        print("数据库文件不存在！")

if __name__ == "__main__":
    check_database()