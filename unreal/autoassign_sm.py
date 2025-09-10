import unreal
import logging
import re

# --- Script Configuration ---

# Set to True to see what the script will do without making any changes.
# Set to False to perform the actual assignments.
DRY_RUN = False

# !!! IMPORTANT !!!
# 1. SET THIS TO THE FULL, EXACT CONTENT BROWSER PATH FOR THE SKELETAL MESH ASSET.
# The path has been corrected to remove the incorrect "/Game/" prefix.
FULL_SKELETAL_MESH_PATH = "/bwfro_01_0140_seqData/Ayon/episodes/ep00/bwfro_00_000/crowd_assets/SkeletalMeshes/tuktukcrowd_rigHigh_v001_fbx"


# --- Helper Function ---

def get_all_descendants(parent_actor):
    """
    Recursively finds all descendant actors of a given parent actor.
    This is a robust way to traverse the hierarchy that works across UE versions.
    """
    descendants = []
    immediate_children = parent_actor.get_attached_actors()
    for child in immediate_children:
        descendants.append(child)
        descendants.extend(get_all_descendants(child))
    return descendants

# --- Main Logic ---

def assign_skeletal_meshes_to_crowd():
    """
    Finds all SkeletalMeshComponents in the selected actor's hierarchy
    and assigns a predefined Skeletal Mesh asset.
    Includes a DRY_RUN mode to test without applying changes.
    """
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s', force=True)

    if DRY_RUN:
        logging.warning("--- Starting Skeletal Mesh Assignment [DRY RUN MODE] ---")
        logging.warning("No changes will be made to the scene.")
    else:
        logging.info("--- Starting Skeletal Mesh Assignment [LIVE MODE] ---")

    # ** Pre-execution check to see if the main asset exists **
    logging.info(f"Verifying asset path: '{FULL_SKELETAL_MESH_PATH}'")
    if not unreal.EditorAssetLibrary.does_asset_exist(FULL_SKELETAL_MESH_PATH):
        logging.error("--- SCRIPT HALTED ---")
        logging.error(f"FATAL: The specified Skeletal Mesh asset could not be found.")
        logging.error("Please verify the FULL_SKELETAL_MESH_PATH variable is correct and try again.")
        return

    skeletal_mesh_asset = unreal.load_asset(FULL_SKELETAL_MESH_PATH)
    if not skeletal_mesh_asset:
        logging.error("--- SCRIPT HALTED ---")
        logging.error(f"FATAL: Asset exists but could not be loaded. Asset may be corrupted or unloadable.")
        return

    logging.info("Asset verified successfully. Proceeding with assignments.")

    # 1. Get the user's current actor selection
    selected_actors = unreal.EditorLevelLibrary.get_selected_level_actors()

    if not selected_actors:
        logging.error("No actor selected. Please select the main parent actor for the crowd and run again.")
        return
    if len(selected_actors) > 1:
        logging.warning("Multiple actors selected. Processing only the first one.")

    parent_actor = selected_actors[0]
    logging.info(f"Parent Actor Selected: '{parent_actor.get_actor_label()}'")

    # 2. Get the full hierarchy
    actors_to_process = [parent_actor] + get_all_descendants(parent_actor)
    logging.info(f"Found {len(actors_to_process)} total actors in the hierarchy to process.")

    success_count = 0
    fail_count = 0 # This should theoretically be 0 now, but good to keep.

    # 3. Iterate through each actor
    for actor in actors_to_process:
        actor_label = actor.get_actor_label()
        skeletal_mesh_component = actor.get_component_by_class(unreal.SkeletalMeshComponent)

        if not skeletal_mesh_component:
            logging.debug(f"Actor '{actor_label}' has no SkeletalMeshComponent. Skipping.")
            continue

        logging.info(f"Processing '{actor_label}'...")

        # 4. Assign the pre-loaded asset
        if DRY_RUN:
            logging.info(f"  -> [DRY RUN] Would assign '{skeletal_mesh_asset.get_name()}' to '{actor_label}'.")
        else:
            skeletal_mesh_component.set_skeletal_mesh(skeletal_mesh_asset)
            logging.info(f"  -> SUCCESS: Assigned '{skeletal_mesh_asset.get_name()}' to '{actor_label}'.")
        success_count += 1

    logging.info("--- Script Finished ---")
    summary_prefix = "[DRY RUN] " if DRY_RUN else ""
    logging.info(f"{summary_prefix}Summary: {success_count} assignments would be successful, {fail_count} would fail.")

# --- Run the main function ---
assign_skeletal_meshes_to_crowd()

