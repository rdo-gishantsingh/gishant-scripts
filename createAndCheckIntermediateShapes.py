import maya.cmds as cmds


def create_non_intermediate_cube():
    """
    Creates a cube with a non-intermediate shape.
    """
    # cmds.polyCube returns [transform_name, polyCube_node_name]
    transform_name, _ = cmds.polyCube(
        name="nonIntermediateCube_GEO#"
    )  # Added # for uniqueness if run multiple times

    # Get the actual shape node from the transform
    shape_nodes = cmds.listRelatives(transform_name, shapes=True, fullPath=True)
    if not shape_nodes:
        cmds.warning(f"Could not find shape node for {transform_name}")
        return None, None

    actual_shape_node = shape_nodes[0]

    # Ensure the shape is non-intermediate (intermediateObject attribute = 0)
    # This is usually the default for new primitives.
    if cmds.attributeQuery("intermediateObject", node=actual_shape_node, exists=True):
        try:
            cmds.setAttr(f"{actual_shape_node}.intermediateObject", 0)
        except RuntimeError as e:
            cmds.warning(
                f"Could not set intermediateObject on {actual_shape_node} (it might be locked or connected): {e}"
            )
    else:
        cmds.warning(
            f"Shape {actual_shape_node} does not have 'intermediateObject' attribute."
        )

    cmds.select(clear=True)
    print(
        f"Created non-intermediate shape: {actual_shape_node} (parent: {transform_name})"
    )
    return transform_name, actual_shape_node


def create_intermediate_cube():
    """
    Creates a cube and marks its shape node as intermediate.
    """
    transform_name, _ = cmds.polyCube(name="intermediateCube_GEO#")  # Added #

    # Get the actual shape node from the transform
    shape_nodes = cmds.listRelatives(transform_name, shapes=True, fullPath=True)
    if not shape_nodes:
        cmds.warning(f"Could not find shape node for {transform_name}")
        return None, None

    actual_shape_node = shape_nodes[0]

    # Mark the shape as intermediate (set intermediateObject attribute = 1)
    if cmds.attributeQuery("intermediateObject", node=actual_shape_node, exists=True):
        try:
            cmds.setAttr(f"{actual_shape_node}.intermediateObject", 1)
        except RuntimeError as e:
            # This can happen if the attribute is connected (e.g., by a deformer)
            # or locked. Forcing it might not always be desired in a real pipeline
            # but for a test script, we're trying to set it directly.
            cmds.warning(
                f"Could not set intermediateObject on {actual_shape_node} (it might be locked or connected): {e}"
            )
            cmds.warning(
                f"Consider creating intermediate objects via construction history for more robust behavior if direct setting fails."
            )

    else:
        cmds.warning(
            f"Shape {actual_shape_node} does not have 'intermediateObject' attribute."
        )

    cmds.select(clear=True)
    print(
        f"Attempted to create intermediate shape: {actual_shape_node} (parent: {transform_name})"
    )
    return transform_name, actual_shape_node


def check_shape_intermediate_status(shape_node):
    """
    Checks and prints whether the given shape node is intermediate.
    """
    if not shape_node or not cmds.objExists(shape_node):
        print(f"Shape node '{shape_node}' does not exist.")
        return None

    if cmds.attributeQuery("intermediateObject", node=shape_node, exists=True):
        try:
            io_value = cmds.getAttr(f"{shape_node}.intermediateObject")
            status = (
                "Intermediate" if io_value else "Non-Intermediate"
            )  # Boolean attribute, 1 is True, 0 is False
            print(
                f"Shape '{shape_node}' is: {status} (intermediateObject = {io_value})"
            )
            return status
        except Exception as e:
            print(f"Error getting 'intermediateObject' for {shape_node}: {e}")
            return None

    else:
        print(f"Shape '{shape_node}' does not have an 'intermediateObject' attribute.")
        return None


def main():
    """
    Main function to create and check cubes.
    """
    print("--- Creating Non-Intermediate Cube ---")
    _, non_intermediate_shape_node = create_non_intermediate_cube()

    print("\n--- Creating Intermediate Cube (by direct attribute set) ---")
    _, intermediate_shape_node = create_intermediate_cube()

    print("\n--- Checking Status ---")
    if non_intermediate_shape_node:
        check_shape_intermediate_status(non_intermediate_shape_node)
    if intermediate_shape_node:
        check_shape_intermediate_status(intermediate_shape_node)

    print("\n--- Note ---")
    print("To visually confirm intermediate objects in Maya's Outliner:")
    print("Go to Outliner menu: Display > Show Intermediate Objects")


main()
