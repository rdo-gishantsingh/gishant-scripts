import os
import shutil
import subprocess
import time

import unreal

# --- CONFIGURATION ---
# IMPORTANT: Change this path to the folder containing your FBX files.
# Use forward slashes '/' for the path.
FBX_SOURCE_FOLDER = "P:/Bollywoof/assets/character/adam/publish/rig/rigHigh/v020"

# The destination folder for the imported assets within your Unreal project's content folder.
# This will be created if it doesn't exist.
IMPORT_DESTINATION = "/Game/Benchmarks/SkeletalMeshes"

# Flag to enable triangulation of FBX files before import
TRIANGULATE_MESH = True

# Path to Maya executable - modify this to match your Maya installation
MAYA_EXECUTABLE = "C:/Program Files/Autodesk/Maya2023/bin/maya"

# Local working directory for copied and processed FBX files
# Handle case where __file__ is not defined (e.g., when running via exec())
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Fallback when __file__ is not defined (running via exec in Unreal console)
    SCRIPT_DIR = "Z:/users/gisi/Dev/scripts"  # Update this to match your script location

WORKING_DIR = os.path.join(SCRIPT_DIR, "fbx_working")
MAYA_TRIANGULATE_SCRIPT = os.path.join(SCRIPT_DIR, "maya_fbx_triangulate.py")
# --- END CONFIGURATION ---

# Check if Maya is available
MAYA_AVAILABLE = True
try:
    result = subprocess.run([MAYA_EXECUTABLE, "--version"], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        MAYA_AVAILABLE = False
except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
    MAYA_AVAILABLE = False

if not MAYA_AVAILABLE:
    print("Warning: Maya not available. Triangulation feature will be disabled.")
    print(f"Make sure Maya is in PATH or update MAYA_EXECUTABLE to point to Maya binary: {MAYA_EXECUTABLE}")


def triangulate_fbx_mesh(input_path, output_path):
    """
    Triangulates the mesh in an FBX file using Maya batch mode.
    Returns True if successful, False otherwise.
    """
    if not MAYA_AVAILABLE:
        unreal.log_warning("Maya not available, skipping triangulation")
        # Copy the original file without triangulation
        shutil.copy2(input_path, output_path)
        return True

    if not os.path.exists(MAYA_TRIANGULATE_SCRIPT):
        unreal.log_error(f"Maya triangulation script not found: {MAYA_TRIANGULATE_SCRIPT}")
        # Copy the original file without triangulation
        shutil.copy2(input_path, output_path)
        return False

    try:
        # Run Maya in batch mode to triangulate the FBX
        cmd = [
            MAYA_EXECUTABLE,
            "-batch",
            "-command",
            f"python(\"exec(open('{MAYA_TRIANGULATE_SCRIPT}').read()); triangulate_fbx_in_maya('{input_path.replace(chr(92), '/')}', '{output_path.replace(chr(92), '/')}')\")",
        ]

        unreal.log(f"Running Maya triangulation: {os.path.basename(input_path)}")

        # Execute Maya batch command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0 and os.path.exists(output_path):
            unreal.log(f"Successfully triangulated: {os.path.basename(input_path)}")
            return True
        else:
            unreal.log_error(f"Maya triangulation failed for {input_path}")
            if result.stderr:
                unreal.log_error(f"Maya error: {result.stderr}")
            # Copy the original file as fallback
            shutil.copy2(input_path, output_path)
            return False

    except subprocess.TimeoutExpired:
        unreal.log_error(f"Maya triangulation timed out for {input_path}")
        # Copy the original file as fallback
        shutil.copy2(input_path, output_path)
        return False
    except Exception as e:
        unreal.log_error(f"Error running Maya triangulation for {input_path}: {str(e)}")
        # Copy the original file as fallback
        shutil.copy2(input_path, output_path)
        return False


def copy_and_process_fbx_files(source_folder, fbx_files):
    """
    Copies FBX files to working directory and optionally triangulates them.
    Returns list of processed file paths.
    """
    # Create working directory if it doesn't exist
    if not os.path.exists(WORKING_DIR):
        os.makedirs(WORKING_DIR)

    processed_files = []

    for fbx_file in fbx_files:
        source_path = os.path.join(source_folder, fbx_file)

        if TRIANGULATE_MESH:
            # Create triangulated version
            base_name = os.path.splitext(fbx_file)[0]
            processed_name = f"{base_name}_triangulated.fbx"
            dest_path = os.path.join(WORKING_DIR, processed_name)

            unreal.log(f"Triangulating: {fbx_file}")
            if triangulate_fbx_mesh(source_path, dest_path):
                processed_files.append(dest_path)
            else:
                unreal.log_error(f"Failed to process: {fbx_file}")
        else:
            # Just copy the original file
            dest_path = os.path.join(WORKING_DIR, fbx_file)
            try:
                shutil.copy2(source_path, dest_path)
                processed_files.append(dest_path)
                unreal.log(f"Copied: {fbx_file}")
            except Exception as e:
                unreal.log_error(f"Failed to copy {fbx_file}: {str(e)}")

    return processed_files


def cleanup_working_directory():
    """
    Cleans up the working directory after processing.
    """
    try:
        if os.path.exists(WORKING_DIR):
            shutil.rmtree(WORKING_DIR)
            unreal.log("Cleaned up working directory")
    except Exception as e:
        unreal.log_warning(f"Failed to clean up working directory: {str(e)}")


def build_skeletal_mesh_import_options():
    """
    Creates and configures the import options for a skeletal mesh.
    We are disabling material/texture import to focus the benchmark purely on the mesh processing time.
    """
    options = unreal.FbxImportUI()
    # General settings
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("import_animations", False)

    # Skeletal Mesh specific settings
    skeletal_mesh_import_data = options.get_editor_property("skeletal_mesh_import_data")
    skeletal_mesh_import_data.set_editor_property("import_morph_targets", True)
    skeletal_mesh_import_data.set_editor_property("update_skeleton_reference_pose", False)

    return options


def build_import_task(filename, destination_path, options):
    """
    Creates an asset import task for a single file.
    """
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", filename)
    task.set_editor_property("destination_path", destination_path)
    # The import options created above
    task.set_editor_property("options", options)
    # Set to True to overwrite existing assets, useful for re-running the benchmark
    task.set_editor_property("replace_existing", True)
    # We don't need to save the assets to disk for a pure benchmark
    task.set_editor_property("save", False)
    # Set automated to True to prevent dialogs
    task.set_editor_property("automated", True)
    return task


def run_benchmark():
    """
    Main function to execute the benchmark process.
    """
    unreal.log("Starting Skeletal Mesh FBX Import Benchmark...")

    if TRIANGULATE_MESH and MAYA_AVAILABLE:
        unreal.log("Triangulation enabled - Maya available")
    elif TRIANGULATE_MESH and not MAYA_AVAILABLE:
        unreal.log("Triangulation enabled but Maya not available - will copy files without triangulation")
    else:
        unreal.log("Triangulation disabled")

    if not os.path.isdir(FBX_SOURCE_FOLDER):
        unreal.log_error(f"Source folder not found: {FBX_SOURCE_FOLDER}")
        unreal.log_error("Please update the FBX_SOURCE_FOLDER variable in the script.")
        return

    fbx_files = [f for f in os.listdir(FBX_SOURCE_FOLDER) if f.lower().endswith(".fbx")]

    if not fbx_files:
        unreal.log_warning(f"No .fbx files found in {FBX_SOURCE_FOLDER}")
        return

    unreal.log(f"Found {len(fbx_files)} FBX files to process")

    # Copy and optionally triangulate FBX files
    processed_files = copy_and_process_fbx_files(FBX_SOURCE_FOLDER, fbx_files)

    if not processed_files:
        unreal.log_error("No files were successfully processed")
        return

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    import_options = build_skeletal_mesh_import_options()

    total_time = 0.0
    imported_count = 0
    all_tasks = []

    # Create import tasks for processed files
    for processed_file in processed_files:
        # Convert to forward slashes for Unreal
        processed_file_path = processed_file.replace("\\", "/")
        task = build_import_task(processed_file_path, IMPORT_DESTINATION, import_options)
        all_tasks.append(task)

    # Unreal's import_asset_tasks is more efficient for batching
    unreal.log(f"Starting import of {len(all_tasks)} processed FBX files...")

    start_time = time.time()

    # Execute all import tasks
    asset_tools.import_asset_tasks(all_tasks)

    end_time = time.time()

    # The result of the import is in the task's 'imported_object_paths' property
    for task in all_tasks:
        if task.get_editor_property("imported_object_paths"):
            imported_count += 1
            filename = os.path.basename(task.get_editor_property("filename"))
            unreal.log(f"Successfully processed import for: {filename}")
        else:
            unreal.log_error(f"Failed to import: {os.path.basename(task.get_editor_property('filename'))}")

    total_time = end_time - start_time
    average_time = total_time / imported_count if imported_count > 0 else 0

    # Clean up working directory
    cleanup_working_directory()

    # --- Summary ---
    unreal.log("\n-----------------------------------------")
    unreal.log("           BENCHMARK COMPLETE            ")
    unreal.log("-----------------------------------------")
    unreal.log(f"Triangulation enabled: {TRIANGULATE_MESH}")
    unreal.log(f"Maya available: {MAYA_AVAILABLE}")
    unreal.log(f"Original files found: {len(fbx_files)}")
    unreal.log(f"Files processed: {len(processed_files)}")
    unreal.log(f"Files imported: {imported_count}/{len(all_tasks)}")
    unreal.log(f"Total time taken: {total_time:.4f} seconds")
    unreal.log(f"Average time per file: {average_time:.4f} seconds")
    unreal.log("-----------------------------------------")


# Execute the main function
run_benchmark()
