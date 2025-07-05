import os
import sys


def find_all_executables_with_paths():
    """
    Finds all unique executable files in the directories listed in the PATH
    environment variable and returns their full paths.

    Returns:
        list: A sorted list of unique full paths to the executables.
    """
    executable_paths = set()
    path_env = os.environ.get("PATH", os.defpath)
    path_dirs = path_env.split(os.pathsep)

    is_windows = sys.platform == "win32"
    if is_windows:
        pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").lower().split(";")

    for directory in path_dirs:
        if not os.path.isdir(directory):
            continue

        try:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)

                if not os.path.isfile(filepath):
                    continue

                # --- Platform-specific check for executability ---
                if is_windows:
                    if any(filename.lower().endswith(ext) for ext in pathext if ext):
                        executable_paths.add(filepath)  # Store the full path
                else:  # For Linux/macOS
                    if os.access(filepath, os.X_OK):
                        executable_paths.add(filepath)  # Store the full path

        except OSError:
            # Ignore directories we can't access
            continue

    return sorted(list(executable_paths))


def search_executables(query, all_exec_paths):
    """
    Searches for a specific executable by name in the list of all paths.

    Args:
        query (str): The name of the executable to search for (case-insensitive).
        all_exec_paths (list): A list of full paths to all executables.

    Returns:
        list: A list of matching full paths.
    """
    query = query.lower().strip()
    # We search the filename part of the path
    return [path for path in all_exec_paths if query in os.path.basename(path).lower()]


print("🔍 Scanning your system's PATH for all executables...")
all_execs_with_paths = find_all_executables_with_paths()

print(f"\n✅ Found {len(all_execs_with_paths)} unique executables.")
print("-" * 40)

print("Example executables found (with full path):")
# Print the first 10 found executables as an example
for path in all_execs_with_paths[:10]:
    print(f"  - {path}")
print("-" * 40)

# --- Interactive Search Feature ---
while True:
    search_term = input("\nEnter an executable name to search for (or type 'exit' to quit): ")
    if search_term.lower() in ["exit", "quit"]:
        break
    if not search_term.strip():
        continue

    results = search_executables(search_term, all_execs_with_paths)

    if results:
        print(f"\nFound {len(results)} match(es) for '{search_term}':")
        for path in results:
            print(f"  -> {path}")
    else:
        print(f"\n❌ No executables found matching '{search_term}'.")

print("\nGoodbye!")
