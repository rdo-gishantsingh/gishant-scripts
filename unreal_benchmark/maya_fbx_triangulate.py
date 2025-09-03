#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Maya FBX Triangulation Tool

This module provides functionality to triangulate FBX files using Maya's batch mode.
It can be used both as a standalone script and as a module imported by other tools.
"""

import argparse
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MayaFBXProcessor:
    """Handles FBX processing operations using Maya"""

    def __init__(self):
        self._maya_initialized = False

    def __enter__(self):
        """Context manager entry - initialize Maya"""
        self._initialize_maya()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup Maya"""
        self._cleanup_maya()

    def _initialize_maya(self) -> None:
        """Initialize Maya standalone"""
        try:
            import maya.standalone
            maya.standalone.initialize()
            self._maya_initialized = True
            logger.info("Maya standalone initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Maya: {e}")
            raise

    def _cleanup_maya(self) -> None:
        """Cleanup Maya standalone"""
        if self._maya_initialized:
            try:
                import maya.standalone
                maya.standalone.uninitialize()
                logger.info("Maya standalone cleanup completed")
            except Exception as e:
                logger.warning(f"Error during Maya cleanup: {e}")

    def triangulate_fbx(self, input_path: Path, output_path: Path) -> bool:
        """
        Triangulate an FBX file using Maya's FBX exporter

        Args:
            input_path: Path to input FBX file
            output_path: Path to output triangulated FBX file

        Returns:
            True if successful, False otherwise
        """
        if not self._maya_initialized:
            logger.error("Maya not initialized")
            return False

        try:
            # Import Maya commands here to ensure Maya is initialized
            import maya.cmds as cmds
            import maya.mel as mel

            # Load FBX plugin
            cmds.loadPlugin("fbxmaya", quiet=True)

            # Clear the scene
            cmds.file(new=True, force=True)

            # Import the FBX file
            logger.info(f"Importing FBX: {input_path}")
            cmds.file(str(input_path), i=True, type="FBX", ignoreVersion=True)

            # Configure FBX export settings for triangulation
            self._setup_export_settings(mel)

            # Select objects for export
            self._select_export_objects(cmds)

            # Export the triangulated FBX
            logger.info(f"Exporting triangulated FBX: {output_path}")
            mel.eval(f'FBXExport -f "{output_path.as_posix()}" -s')

            logger.info(f"Successfully triangulated: {input_path.name}")
            return True

        except Exception as e:
            logger.error(f"Error triangulating {input_path}: {e}")
            return False

    def _setup_export_settings(self, mel) -> None:
        """Configure FBX export settings for optimal triangulation"""
        # Reset export settings
        mel.eval("FBXResetExport")

        # Triangulation and geometry settings
        mel.eval("FBXExportTriangulate -v true")  # Enable triangulation
        mel.eval("FBXExportSmoothingGroups -v true")
        mel.eval("FBXExportHardEdges -v false")
        mel.eval("FBXExportTangents -v false")
        mel.eval("FBXExportSmoothMesh -v true")
        mel.eval("FBXExportInstances -v false")

        # Animation and rigging settings
        mel.eval("FBXExportBakeComplexAnimation -v false")
        mel.eval("FBXExportShapes -v true")  # Blend shapes
        mel.eval("FBXExportSkins -v true")   # Skin weights
        mel.eval("FBXExportConstraints -v false")

        # Exclude unnecessary data
        mel.eval("FBXExportLights -v false")
        mel.eval("FBXExportEmbeddedTextures -v false")

        # General export settings
        mel.eval("FBXExportUseSceneName -v false")
        mel.eval("FBXExportQuaternion -v euler")
        mel.eval("FBXExportIncludeChildren -v true")
        mel.eval("FBXExportInputConnections -v true")
        mel.eval("FBXExportUpAxis -v y")
        mel.eval("FBXExportFileVersion -v FBX202000")
        mel.eval("FBXExportSkeletonDefinitions -v false")

        # UI settings
        mel.eval("FBXExportShowUI -v false")
        mel.eval("FBXExportGenerateLog -v false")

    def _select_export_objects(self, cmds) -> None:
        """Select appropriate objects for export"""
        # Find relevant objects for export
        relevant_objects = cmds.ls(dag=True, visible=True, type=["mesh", "joint", "transform"])

        if relevant_objects:
            cmds.select(relevant_objects, replace=True)
            logger.info(f"Selected {len(relevant_objects)} objects for export")
        else:
            # Fallback to select all if no specific objects found
            cmds.select(all=True)
            logger.info("Selected all objects for export")


def triangulate_fbx_in_maya(input_fbx: str, output_fbx: str) -> bool:
    """
    Main function to triangulate an FBX file using Maya

    Args:
        input_fbx: Path to input FBX file (string for backward compatibility)
        output_fbx: Path to output triangulated FBX file (string for backward compatibility)

    Returns:
        True if successful, False otherwise
    """
    input_path = Path(input_fbx)
    output_path = Path(output_fbx)

    # Validate input
    if not input_path.exists():
        logger.error(f"Input file does not exist: {input_path}")
        return False

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Process the file
    try:
        with MayaFBXProcessor() as processor:
            return processor.triangulate_fbx(input_path, output_path)
    except Exception as e:
        logger.error(f"Failed to process {input_path}: {e}")
        return False


def main() -> None:
    """Main function for command line usage"""
    parser = argparse.ArgumentParser(description="Triangulate FBX files using Maya")
    parser.add_argument("input_fbx", help="Input FBX file path")
    parser.add_argument("output_fbx", help="Output triangulated FBX file path")

    args = parser.parse_args()

    input_path = Path(args.input_fbx)
    output_path = Path(args.output_fbx)

    if not input_path.exists():
        logger.error(f"Input file does not exist: {input_path}")
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    success = triangulate_fbx_in_maya(str(input_path), str(output_path))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
