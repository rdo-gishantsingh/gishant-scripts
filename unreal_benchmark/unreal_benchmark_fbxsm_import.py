"""
Unreal Engine FBX Skeletal Mesh Import Benchmark Tool

This script benchmarks the import performance of FBX skeletal meshes into Unreal Engine,
with optional triangulation using Maya.
"""

# Run this in Unreal Console
# exec(open("C:/Users/gisi/Dev/repos/gishant-scripts/unreal_benchmark/unreal_benchmark_fbxsm_import.py").read())

import shutil
import subprocess
import time
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

import unreal


class LogLevel(Enum):
    """Log level enumeration"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class BenchmarkConfig:
    """Configuration class for benchmark settings"""

    # IMPORTANT: Change this path to the folder containing your FBX files
    fbx_source_folder: str = "P:/Bollywoof/assets/character/adam/publish/rig/rigHigh/v020"

    # Destination folder for imported assets within Unreal project
    import_destination: str = "/Game/Benchmarks/SkeletalMeshes"

    # Enable triangulation of FBX files before import
    triangulate_mesh: bool = True

    # Path to Maya executable
    maya_executable: str = "C:/Program Files/Autodesk/Maya2023/bin/maya"

    # Cache directory - update this to match your cache location
    cache_dir: str = "Z:/users/gisi/Dev/cache"

    # Derived paths
    @property
    def working_dir(self) -> Path:
        return Path(self.cache_dir) / "fbx_working"

    @property
    def maya_triangulate_script(self) -> Path:
        return Path(self.cache_dir) / "maya_fbx_triangulate.py"

    # Process timeouts
    maya_timeout: int = 300  # 5 minutes
    maya_version_check_timeout: int = 30


class Logger:
    """Unified logging interface for Unreal Engine"""

    @staticmethod
    def log(message: str, level: LogLevel = LogLevel.INFO) -> None:
        """Log a message with specified level"""
        if level == LogLevel.INFO:
            unreal.log(message)
        elif level == LogLevel.WARNING:
            unreal.log_warning(message)
        elif level == LogLevel.ERROR:
            unreal.log_error(message)

class MayaChecker:
    """Handles Maya availability checking"""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self._is_available: Optional[bool] = None

    @property
    def is_available(self) -> bool:
        """Check if Maya is available and cache the result"""
        if self._is_available is None:
            self._is_available = self._check_maya_availability()
        return self._is_available

    def _check_maya_availability(self) -> bool:
        """Check if Maya executable is available"""
        try:
            result = subprocess.run(
                [self.config.maya_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=self.config.maya_version_check_timeout
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False


class MayaTriangulator:
    """Handles FBX triangulation using Maya"""

    def __init__(self, config: BenchmarkConfig, maya_checker: MayaChecker):
        self.config = config
        self.maya_checker = maya_checker

    def triangulate_fbx(self, input_path: Path, output_path: Path) -> bool:
        """
        Triangulates mesh in FBX file using Maya batch mode

        Args:
            input_path: Path to input FBX file
            output_path: Path to output triangulated FBX file

        Returns:
            True if successful, False otherwise
        """
        if not self.maya_checker.is_available:
            Logger.log("Maya not available, skipping triangulation", LogLevel.WARNING)
            return self._copy_original(input_path, output_path)

        if not self.config.maya_triangulate_script.exists():
            Logger.log(
                f"Maya triangulation script not found: {self.config.maya_triangulate_script}",
                LogLevel.ERROR
            )
            return self._copy_original(input_path, output_path)

        return self._run_maya_triangulation(input_path, output_path)

    def _copy_original(self, input_path: Path, output_path: Path) -> bool:
        """Copy original file without triangulation"""
        try:
            shutil.copy2(input_path, output_path)
            return True
        except Exception as e:
            Logger.log(f"Failed to copy file {input_path}: {e}", LogLevel.ERROR)
            return False

    def _run_maya_triangulation(self, input_path: Path, output_path: Path) -> bool:
        """Execute Maya triangulation process"""
        try:
            cmd = [
                self.config.maya_executable,
                "-batch",
                "-command",
                f"python(\"exec(open('{self.config.maya_triangulate_script}').read()); "
                f"triangulate_fbx_in_maya('{input_path.as_posix()}', '{output_path.as_posix()}')\")",
            ]

            Logger.log(f"Running Maya triangulation: {input_path.name}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.maya_timeout
            )

            if result.returncode == 0 and output_path.exists():
                Logger.log(f"Successfully triangulated: {input_path.name}")
                return True
            else:
                Logger.log(f"Maya triangulation failed for {input_path}", LogLevel.ERROR)
                if result.stderr:
                    Logger.log(f"Maya error: {result.stderr}", LogLevel.ERROR)
                return self._copy_original(input_path, output_path)

        except subprocess.TimeoutExpired:
            Logger.log(f"Maya triangulation timed out for {input_path}", LogLevel.ERROR)
            return self._copy_original(input_path, output_path)
        except Exception as e:
            Logger.log(f"Error running Maya triangulation for {input_path}: {e}", LogLevel.ERROR)
            return self._copy_original(input_path, output_path)


class FileProcessor:
    """Handles file operations and processing"""

    def __init__(self, config: BenchmarkConfig, triangulator: MayaTriangulator):
        self.config = config
        self.triangulator = triangulator

    def setup_working_directory(self) -> None:
        """Create working directory if it doesn't exist"""
        self.config.working_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_working_directory(self) -> None:
        """Clean up the working directory after processing"""
        try:
            if self.config.working_dir.exists():
                shutil.rmtree(self.config.working_dir)
                Logger.log("Cleaned up working directory")
        except Exception as e:
            Logger.log(f"Failed to clean up working directory: {e}", LogLevel.WARNING)

    def find_fbx_files(self, source_folder: Path) -> List[str]:
        """Find all FBX files in the source folder"""
        if not source_folder.is_dir():
            return []
        return [f.name for f in source_folder.iterdir() if f.suffix.lower() == ".fbx"]

    def process_fbx_files(self, source_folder: Path, fbx_files: List[str]) -> List[Path]:
        """
        Process FBX files by copying and optionally triangulating them

        Args:
            source_folder: Source directory containing FBX files
            fbx_files: List of FBX filenames to process

        Returns:
            List of processed file paths
        """
        self.setup_working_directory()
        processed_files = []

        for fbx_file in fbx_files:
            source_path = source_folder / fbx_file
            processed_path = self._process_single_file(source_path)

            if processed_path:
                processed_files.append(processed_path)
            else:
                Logger.log(f"Failed to process: {fbx_file}", LogLevel.ERROR)

        return processed_files

    def _process_single_file(self, source_path: Path) -> Optional[Path]:
        """Process a single FBX file"""
        if self.config.triangulate_mesh:
            return self._triangulate_file(source_path)
        else:
            return self._copy_file(source_path)

    def _triangulate_file(self, source_path: Path) -> Optional[Path]:
        """Triangulate a single FBX file"""
        base_name = source_path.stem
        processed_name = f"{base_name}_triangulated.fbx"
        dest_path = self.config.working_dir / processed_name

        Logger.log(f"Triangulating: {source_path.name}")
        if self.triangulator.triangulate_fbx(source_path, dest_path):
            return dest_path
        return None

    def _copy_file(self, source_path: Path) -> Optional[Path]:
        """Copy a single FBX file without triangulation"""
        dest_path = self.config.working_dir / source_path.name
        try:
            shutil.copy2(source_path, dest_path)
            Logger.log(f"Copied: {source_path.name}")
            return dest_path
        except Exception as e:
            Logger.log(f"Failed to copy {source_path.name}: {e}", LogLevel.ERROR)
            return None


class UnrealImportOptions:
    """Handles Unreal Engine import options configuration"""

    @staticmethod
    def create_skeletal_mesh_options() -> unreal.FbxImportUI:
        """
        Creates and configures import options for skeletal mesh
        Materials/textures are disabled to focus benchmark on mesh processing
        """
        options = unreal.FbxImportUI()

        # General settings
        options.set_editor_property("import_as_skeletal", True)
        options.set_editor_property("import_mesh", True)
        options.set_editor_property("import_materials", False)
        options.set_editor_property("import_textures", False)
        options.set_editor_property("import_animations", False)

        # Skeletal mesh specific settings
        skeletal_mesh_import_data = options.get_editor_property("skeletal_mesh_import_data")
        skeletal_mesh_import_data.set_editor_property("import_morph_targets", True)
        skeletal_mesh_import_data.set_editor_property("update_skeleton_reference_pose", False)

        return options

    @staticmethod
    def create_import_task(filename: str, destination_path: str, options: unreal.FbxImportUI) -> unreal.AssetImportTask:
        """Create an asset import task for a single file"""
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", filename)
        task.set_editor_property("destination_path", destination_path)
        task.set_editor_property("options", options)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", False)  # Don't save for pure benchmark
        task.set_editor_property("automated", True)  # Prevent dialogs
        return task


@dataclass
class BenchmarkResults:
    """Container for benchmark results"""
    triangulation_enabled: bool
    maya_available: bool
    original_files_found: int
    files_processed: int
    files_imported: int
    total_time: float

    @property
    def average_time_per_file(self) -> float:
        """Calculate average time per imported file"""
        return self.total_time / self.files_imported if self.files_imported > 0 else 0.0

    def print_summary(self) -> None:
        """Print benchmark results summary"""
        Logger.log("\n-----------------------------------------")
        Logger.log("           BENCHMARK COMPLETE            ")
        Logger.log("-----------------------------------------")
        Logger.log(f"Triangulation enabled: {self.triangulation_enabled}")
        Logger.log(f"Maya available: {self.maya_available}")
        Logger.log(f"Original files found: {self.original_files_found}")
        Logger.log(f"Files processed: {self.files_processed}")
        Logger.log(f"Files imported: {self.files_imported}")
        Logger.log(f"Total time taken: {self.total_time:.4f} seconds")
        Logger.log(f"Average time per file: {self.average_time_per_file:.4f} seconds")
        Logger.log("-----------------------------------------")


class FBXBenchmarkRunner:
    """Main benchmark runner orchestrating the entire process"""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.maya_checker = MayaChecker(config)
        self.triangulator = MayaTriangulator(config, self.maya_checker)
        self.file_processor = FileProcessor(config, self.triangulator)

    def run(self) -> BenchmarkResults:
        """Execute the complete benchmark process"""
        Logger.log("Starting Skeletal Mesh FBX Import Benchmark...")

        self._log_initial_status()

        # Validate source folder
        source_folder = Path(self.config.fbx_source_folder)
        if not source_folder.is_dir():
            Logger.log(f"Source folder not found: {source_folder}", LogLevel.ERROR)
            Logger.log("Please update the fbx_source_folder in the configuration.", LogLevel.ERROR)
            return self._create_failed_results()

        # Find FBX files
        fbx_files = self.file_processor.find_fbx_files(source_folder)
        if not fbx_files:
            Logger.log(f"No .fbx files found in {source_folder}", LogLevel.WARNING)
            return self._create_failed_results()

        Logger.log(f"Found {len(fbx_files)} FBX files to process")

        # Process files
        processed_files = self.file_processor.process_fbx_files(source_folder, fbx_files)
        if not processed_files:
            Logger.log("No files were successfully processed", LogLevel.ERROR)
            return self._create_failed_results()

        # Import into Unreal
        import_results = self._import_to_unreal(processed_files)

        # Cleanup
        self.file_processor.cleanup_working_directory()

        # Create and return results
        results = BenchmarkResults(
            triangulation_enabled=self.config.triangulate_mesh,
            maya_available=self.maya_checker.is_available,
            original_files_found=len(fbx_files),
            files_processed=len(processed_files),
            files_imported=import_results['imported_count'],
            total_time=import_results['total_time']
        )

        results.print_summary()
        return results

    def _log_initial_status(self) -> None:
        """Log initial status of Maya and triangulation"""
        if self.config.triangulate_mesh and self.maya_checker.is_available:
            Logger.log("Triangulation enabled - Maya available")
        elif self.config.triangulate_mesh and not self.maya_checker.is_available:
            Logger.log("Triangulation enabled but Maya not available - will copy files without triangulation")
        else:
            Logger.log("Triangulation disabled")

    def _create_failed_results(self) -> BenchmarkResults:
        """Create results object for failed benchmark"""
        return BenchmarkResults(
            triangulation_enabled=self.config.triangulate_mesh,
            maya_available=self.maya_checker.is_available,
            original_files_found=0,
            files_processed=0,
            files_imported=0,
            total_time=0.0
        )

    def _import_to_unreal(self, processed_files: List[Path]) -> dict:
        """Import processed files into Unreal Engine"""
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        import_options = UnrealImportOptions.create_skeletal_mesh_options()

        # Create import tasks
        all_tasks = []
        for processed_file in processed_files:
            processed_file_path = processed_file.as_posix()
            task = UnrealImportOptions.create_import_task(
                processed_file_path,
                self.config.import_destination,
                import_options
            )
            all_tasks.append(task)

        Logger.log(f"Starting import of {len(all_tasks)} processed FBX files...")

        # Execute import
        start_time = time.time()
        asset_tools.import_asset_tasks(all_tasks)
        end_time = time.time()

        # Count successful imports
        imported_count = 0
        for task in all_tasks:
            if task.get_editor_property("imported_object_paths"):
                imported_count += 1
                filename = Path(task.get_editor_property("filename")).name
                Logger.log(f"Successfully processed import for: {filename}")
            else:
                filename = Path(task.get_editor_property("filename")).name
                Logger.log(f"Failed to import: {filename}", LogLevel.ERROR)

        return {
            'imported_count': imported_count,
            'total_time': end_time - start_time
        }


def main() -> None:
    """Main function to execute the benchmark"""
    # Create configuration - modify these values as needed
    config = BenchmarkConfig()

    # Initialize and run benchmark
    runner = FBXBenchmarkRunner(config)
    results = runner.run()

    # Results are automatically printed in the run method
    return results


# Execute the main function
if __name__ == "__main__":
    main()
else:
    # For direct execution in Unreal Python console
    main()
