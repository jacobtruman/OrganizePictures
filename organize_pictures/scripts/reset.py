import os
import shutil
import sqlite3


def clear(_relative_path: str):
    # Get the absolute path
    absolute_path = os.path.abspath(os.path.join(os.path.dirname(__file__), _relative_path))
    if not os.path.isdir(absolute_path):
        print(f"Path not found: {absolute_path}")
        return

    # Clear out the contents of the directory but keep the directory itself
    for filename in os.listdir(absolute_path):
        file_path = os.path.join(absolute_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')


def copy_files(src_path: str, dest_relative_path: str):
    # Get the absolute paths
    src_absolute_path = os.path.abspath(src_path)
    dest_absolute_path = os.path.abspath(os.path.join(os.path.dirname(__file__), dest_relative_path))

    if not os.path.isdir(src_absolute_path):
        print(f"Source path not found: {src_absolute_path}")
        return

    if not os.path.isdir(dest_absolute_path):
        os.makedirs(dest_absolute_path)

    # Copy the contents of the source directory to the destination directory
    for filename in os.listdir(src_absolute_path):
        src_file_path = os.path.join(src_absolute_path, filename)
        dest_file_path = os.path.join(dest_absolute_path, filename)
        try:
            if os.path.isfile(src_file_path) or os.path.islink(src_file_path):
                shutil.copy2(src_file_path, dest_file_path)
            elif os.path.isdir(src_file_path):
                shutil.copytree(src_file_path, dest_file_path)
        except Exception as e:
            print(f'Failed to copy {src_file_path} to {dest_file_path}. Reason: {e}')


# Define the relative paths to the directories to be cleared and copied
relative_paths_to_clear = ['../renamed', './Disneyland', './paris', './india']
paths = {
    '/Users/jatruman/Pictures/paris': './paris',
    # '/Users/jatruman/Pictures/india': './india',
    # '/Users/jatruman/Pictures/Disneyland': './Disneyland',
}

for relative_path in relative_paths_to_clear:
    print(f"Clearing: {relative_path}")
    clear(relative_path)

for src_path, dest_relative_path in paths.items():
    print(f"Copying files from {src_path} to {dest_relative_path}")
    copy_files(src_path, dest_relative_path)


def delete_all_records(db_relative_path: str):
    table_name = "image_hashes"
    # Get the absolute path
    db_absolute_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_relative_path))

    # Connect to the SQLite database
    try:
        conn = sqlite3.connect(db_absolute_path)
        cursor = conn.cursor()

        # Delete all records from the relevant table(s)
        cursor.execute(f"DELETE FROM {table_name}")

        # Commit the changes
        conn.commit()
        print(f"All records deleted from the database: {db_absolute_path}")

    except sqlite3.Error as e:
        print(f"Failed to delete records from {db_absolute_path}. Reason: {e}")

    finally:
        if conn:
            conn.close()


# Define the relative path to the database file
db_relative_path = '../pictures.db'

# Delete all records in the database
delete_all_records(db_relative_path)