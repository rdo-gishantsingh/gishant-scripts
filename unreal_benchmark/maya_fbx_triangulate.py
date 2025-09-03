#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Maya standalone script to triangulate FBX files.
This script can be run with Maya in batch mode to triangulate FBX files.
"""

import argparse
import os
import sys


def triangulate_fbx_in_maya(input_fbx, output_fbx):
    """
    Triangulates an FBX file using Maya's FBX exporter.

    Args:
        input_fbx (str): Path to input FBX file
        output_fbx (str): Path to output triangulated FBX file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import maya.standalone

        maya.standalone.initialize()

        import maya.cmds as cmds
        import maya.mel as mel

        # Load FBX plugin
        cmds.loadPlugin("fbxmaya", quiet=True)

        # Clear the scene
        cmds.file(new=True, force=True)

        # Import the FBX file
        print(f"Importing FBX: {input_fbx}")
        cmds.file(input_fbx, i=True, type="FBX", ignoreVersion=True)

        # Setup FBX export settings for triangulation
        mel.eval("FBXResetExport")

        # Configure FBX export settings
        mel.eval("FBXExportTriangulate -v true")  # Enable triangulation
        mel.eval("FBXExportSmoothingGroups -v true")
        mel.eval("FBXExportHardEdges -v false")
        mel.eval("FBXExportTangents -v false")
        mel.eval("FBXExportSmoothMesh -v true")
        mel.eval("FBXExportInstances -v false")
        mel.eval("FBXExportBakeComplexAnimation -v false")
        mel.eval("FBXExportUseSceneName -v false")
        mel.eval("FBXExportQuaternion -v euler")
        mel.eval("FBXExportShapes -v true")
        mel.eval("FBXExportSkins -v true")
        mel.eval("FBXExportConstraints -v false")
        mel.eval("FBXExportLights -v false")
        mel.eval("FBXExportEmbeddedTextures -v false")
        mel.eval("FBXExportIncludeChildren -v true")
        mel.eval("FBXExportInputConnections -v true")
        mel.eval("FBXExportUpAxis -v y")
        mel.eval("FBXExportFileVersion -v FBX202000")
        mel.eval("FBXExportSkeletonDefinitions -v false")
        mel.eval("FBXExportShowUI -v false")
        mel.eval("FBXExportGenerateLog -v false")

        # Select all objects for export
        all_objects = cmds.ls(dag=True, visible=True, type=["mesh", "joint", "transform"])
        if all_objects:
            cmds.select(all_objects, replace=True)
        else:
            # If no specific objects, select all
            cmds.select(all=True)

        # Export the triangulated FBX
        print(f"Exporting triangulated FBX: {output_fbx}")
        output_fbx_normalized = output_fbx.replace("\\", "/")
        mel.eval(f'FBXExport -f "{output_fbx_normalized}" -s')

        print(f"Successfully triangulated: {os.path.basename(input_fbx)}")
        return True

    except Exception as e:
        print(f"Error triangulating {input_fbx}: {str(e)}")
        return False
    finally:
        try:
            maya.standalone.uninitialize()
        except:
            pass


def main():
    """Main function for command line usage."""
    parser = argparse.ArgumentParser(description="Triangulate FBX files using Maya")
    parser.add_argument("input_fbx", help="Input FBX file path")
    parser.add_argument("output_fbx", help="Output triangulated FBX file path")

    args = parser.parse_args()

    if not os.path.exists(args.input_fbx):
        print(f"Error: Input file does not exist: {args.input_fbx}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output_fbx)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    success = triangulate_fbx_in_maya(args.input_fbx, args.output_fbx)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
