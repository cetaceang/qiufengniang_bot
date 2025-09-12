import sqlite3
import json
import os

def diagnose_database():
    """
    Connects to the database and runs a few queries to diagnose the data integrity.
    """
    db_path = os.path.join('data', 'world_book.sqlite3')
    if not os.path.exists(db_path):
        print(f"Database file not found at '{db_path}'.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- Diagnosing Database ---")

    # 1. Check a community member
    print("\n[1] Checking a community member (ID: huangdoufen_1)...")
    cursor.execute("SELECT * FROM community_members WHERE id = ?", ('huangdoufen_1',))
    member = cursor.fetchone()
    if member:
        print("  - Member found:")
        print(f"    ID: {member[0]}, Title: {member[1]}, Discord ID: {member[2]}")
        content = json.loads(member[5])
        print(f"    Content: {content}")
        
        cursor.execute("SELECT nickname FROM member_discord_nicknames WHERE member_id = ?", ('huangdoufen_1',))
        nicknames = cursor.fetchall()
        print(f"  - Nicknames: {[n[0] for n in nicknames]}")
    else:
        print("  - Member 'huangdoufen_1' not found!")

    # 2. Check a general knowledge entry
    print("\n[2] Checking a general knowledge entry (ID: reverse_proxy)...")
    cursor.execute("""
        SELECT gk.id, gk.title, gk.name, c.name 
        FROM general_knowledge gk
        JOIN categories c ON gk.category_id = c.id
        WHERE gk.id = ?
    """, ('reverse_proxy',))
    entry = cursor.fetchone()
    if entry:
        print("  - Entry found:")
        print(f"    ID: {entry[0]}, Title: {entry[1]}, Name: {entry[2]}, Category: {entry[3]}")
        
        cursor.execute("SELECT alias FROM aliases WHERE entry_id = ?", ('reverse_proxy',))
        aliases = cursor.fetchall()
        print(f"  - Aliases: {[a[0] for a in aliases]}")
    else:
        print("  - Entry 'reverse_proxy' not found!")
        
    # 3. Check a slang entry with refers_to
    print("\n[3] Checking a slang entry (ID: hachimi)...")
    cursor.execute("SELECT id, name FROM general_knowledge WHERE id = ?", ('hachimi',))
    slang = cursor.fetchone()
    if slang:
        print("  - Slang found:")
        print(f"    ID: {slang[0]}, Name: {slang[1]}")
        
        cursor.execute("SELECT reference FROM knowledge_refers_to WHERE entry_id = ?", ('hachimi',))
        refs = cursor.fetchall()
        print(f"  - Refers to: {[r[0] for r in refs]}")
    else:
        print("  - Slang 'hachimi' not found!")

    # 4. Count total entries in key tables
    print("\n[4] Counting total entries...")
    cursor.execute("SELECT COUNT(*) FROM community_members")
    print(f"  - Total community members: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM general_knowledge")
    print(f"  - Total general knowledge entries: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM categories")
    print(f"  - Total categories: {cursor.fetchone()[0]}")


    print("\n--- Diagnosis Complete ---")
    conn.close()

if __name__ == '__main__':
    diagnose_database()
