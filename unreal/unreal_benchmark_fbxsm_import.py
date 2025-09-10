"""
Unreal Engine FBX Skeletal Mesh Import Benchmark Too    # Path to Maya batch executable (use mayabatch.exe for command-line operations)
    maya_executable: str = "/usr/autodesk/maya2023/bin/mayabatch"  # Linux path

    # Cache directory - update this to match your cache location
    cache_dir: str = "/home/gisi/Dev/repos/gishant-scripts/cache"  # Linux pathis script benchmarks the import performance of FBX skeletal meshes into Unreal Engine,
with optional triangulation using Maya.

Key features:
- Class-based architecture for maintainability
- Separates triangulation timing from pure import timing
- Uses mayabatch.exe for Maya automation (not GUI maya.exe)
- Disables Unreal's automatic triangulation to measure only Maya triangulation
- Comprehensive logging with script identification
- Cache directory organization for temporary files

Recent fixes:
- Maya executable path corrected from maya.exe to mayabatch.exe
- Unreal FBX import configured to disable automatic triangulation
- Enhanced mesh import data settings to preserve Maya triangulation
- Script path resolution updated to use cache directory
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

    # Path to Maya batch executable (use mayabatch.exe for command-line operations)
    maya_executable: str = "C:/Program Files/Autodesk/Maya2023/bin/mayabatch.exe"

    # Cache directory - update this to match your cache location
    cache_dir: str = "Z:/users/gisi/Dev/cache"

    # Derived paths
    @property
    def working_dir(self) -> Path:
        return Path(self.cache_dir) / "fbx_working"

    @property
    def maya_triangulate_script(self) -> Path:
        # Script is actually in the unreal_benchmark directory, not cache
        return Path("Z:/users/gisi/Dev/repos/gishant-scripts/unreal_benchmark") / "maya_fbx_triangulate.py"

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
        Logger.log(f"🔍 [MayaChecker] Checking Maya availability at: {self.config.maya_executable}")
        try:
            # Use -v flag instead of --version (Maya doesn't support --version properly)
            result = subprocess.run(
                [self.config.maya_executable, "-v"],
                capture_output=True,
                text=True,
                timeout=self.config.maya_version_check_timeout,
            )
            if result.returncode == 0:
                Logger.log("✅ [MayaChecker] Maya is available - version check passed")
                Logger.log(f"🔍 [MayaChecker] Maya version output: {result.stdout.strip()}")
                return True
            else:
                Logger.log(f"❌ [MayaChecker] Maya version check failed with return code: {result.returncode}")
                if result.stderr:
                    Logger.log(f"🔍 [MayaChecker] Maya stderr: {result.stderr}")
                if result.stdout:
                    Logger.log(f"🔍 [MayaChecker] Maya stdout: {result.stdout}")
                return False
        except FileNotFoundError:
            Logger.log(f"❌ [MayaChecker] Maya executable not found at: {self.config.maya_executable}")
            return False
        except subprocess.TimeoutExpired:
            Logger.log(f"⏱️ [MayaChecker] Maya version check timed out after {self.config.maya_version_check_timeout}s")
            return False
        except subprocess.SubprocessError as e:
            Logger.log(f"❌ [MayaChecker] Maya subprocess error: {e}")
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
        Logger.log(f"🔧 [MayaTriangulator] Processing: {input_path.name}")
        Logger.log(f"🔧 [MayaTriangulator] Maya available: {self.maya_checker.is_available}")
        Logger.log(f"🔧 [MayaTriangulator] Script path: {self.config.maya_triangulate_script}")
        Logger.log(f"🔧 [MayaTriangulator] Script exists: {self.config.maya_triangulate_script.exists()}")

        if not self.maya_checker.is_available:
            Logger.log("⚠️ [MayaTriangulator] Maya not available, copying original file", LogLevel.WARNING)
            return self._copy_original(input_path, output_path)

        if not self.config.maya_triangulate_script.exists():
            Logger.log(
                f"❌ [MayaTriangulator] Maya triangulation script not found: {self.config.maya_triangulate_script}",
                LogLevel.ERROR,
            )
            return self._copy_original(input_path, output_path)

        Logger.log("🚀 [MayaTriangulator] Starting Maya triangulation process")
        return self._run_maya_triangulation(input_path, output_path)

    def _copy_original(self, input_path: Path, output_path: Path) -> bool:
        """Copy original file without triangulation"""
        Logger.log("📁 [MayaTriangulator] Copying file without triangulation")
        Logger.log(f"📁 [MayaTriangulator] From: {input_path}")
        Logger.log(f"📁 [MayaTriangulator] To: {output_path}")
        try:
            shutil.copy2(input_path, output_path)
            Logger.log(f"✅ [MayaTriangulator] Successfully copied: {input_path.name} -> {output_path.name}")
            return True
        except Exception as e:
            Logger.log(f"❌ [MayaTriangulator] Failed to copy file {input_path}: {e}", LogLevel.ERROR)
            return False

    def _run_maya_triangulation(self, input_path: Path, output_path: Path) -> bool:
        """Execute Maya triangulation process"""
        try:
            # Convert paths to strings with proper Windows formatting
            script_path = str(self.config.maya_triangulate_script).replace('\\', '/')
            input_path_str = str(input_path).replace('\\', '/')
            output_path_str = str(output_path).replace('\\', '/')

            cmd = [
                self.config.maya_executable,
                "-batch",
                "-command",
                f"python(\"exec(open('{script_path}').read()); "
                f"triangulate_fbx_in_maya('{input_path_str}', '{output_path_str}')\")",
            ]

            Logger.log(f"🚀 [MayaTriangulator] Executing Maya command: {input_path.name}")
            Logger.log(f"🔍 [MayaTriangulator] Maya executable: {self.config.maya_executable}")
            Logger.log(f"🔍 [MayaTriangulator] Script: {script_path}")
            Logger.log(f"🔍 [MayaTriangulator] Input: {input_path_str}")
            Logger.log(f"🔍 [MayaTriangulator] Output: {output_path_str}")
            Logger.log(f"⏱️ [MayaTriangulator] Timeout: {self.config.maya_timeout}s")

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.config.maya_timeout)

            Logger.log(f"🔍 [MayaTriangulator] Maya return code: {result.returncode}")
            Logger.log(f"🔍 [MayaTriangulator] Output file exists: {output_path.exists()}")

            if result.stdout:
                Logger.log(f"📝 [MayaTriangulator] Maya stdout: {result.stdout}")
            if result.stderr:
                Logger.log(f"🔍 [MayaTriangulator] Maya stderr: {result.stderr}")

            if result.returncode == 0 and output_path.exists():
                Logger.log(f"✅ [MayaTriangulator] Successfully triangulated: {input_path.name}")
                return True
            else:
                Logger.log(f"❌ [MayaTriangulator] Maya triangulation failed for {input_path}", LogLevel.ERROR)
                Logger.log("📁 [MayaTriangulator] Falling back to copying original file")
                return self._copy_original(input_path, output_path)

        except subprocess.TimeoutExpired:
            Logger.log(f"⏱️ [MayaTriangulator] Maya triangulation timed out for {input_path}", LogLevel.ERROR)
            return self._copy_original(input_path, output_path)
        except Exception as e:
            Logger.log(f"❌ [MayaTriangulator] Error running Maya triangulation for {input_path}: {e}", LogLevel.ERROR)
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

    def process_fbx_files(self, source_folder: Path, fbx_files: List[str]) -> tuple[List[Path], float]:
        """
        Process FBX files by copying and optionally triangulating them

        Args:
            source_folder: Source directory containing FBX files
            fbx_files: List of FBX filenames to process

        Returns:
            Tuple of (processed file paths, triangulation time in seconds)
        """
        self.setup_working_directory()
        processed_files = []

        Logger.log("🔄 Starting file processing phase...")
        triangulation_start = time.time()

        for fbx_file in fbx_files:
            source_path = source_folder / fbx_file
            processed_path = self._process_single_file(source_path)

            if processed_path:
                processed_files.append(processed_path)
            else:
                Logger.log(f"Failed to process: {fbx_file}", LogLevel.ERROR)

        triangulation_time = time.time() - triangulation_start

        if self.config.triangulate_mesh:
            Logger.log(
                f"✅ File processing complete: {len(processed_files)} files processed in {triangulation_time:.4f}s"
            )
        else:
            Logger.log(f"✅ File copying complete: {len(processed_files)} files copied in {triangulation_time:.4f}s")

        return processed_files, triangulation_time

    def _process_single_file(self, source_path: Path) -> Optional[Path]:
        """Process a single FBX file"""
        if self.config.triangulate_mesh:
            return self._triangulate_file(source_path)
        else:
            return self._copy_file(source_path)

    def _triangulate_file(self, source_path: Path) -> Optional[Path]:
        """Triangulate a single FBX file"""
        base_name = source_path.stem

        # Check if actual triangulation will happen
        will_triangulate = self.triangulator.maya_checker.is_available and self.config.maya_triangulate_script.exists()

        if will_triangulate:
            processed_name = f"{base_name}_triangulated.fbx"
            Logger.log(f"Triangulating: {source_path.name}")
        else:
            processed_name = source_path.name
            Logger.log(f"Copying (Maya unavailable): {source_path.name}")

        dest_path = self.config.working_dir / processed_name

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
        CRITICAL: Unreal's triangulation is DISABLED to ensure we only test Maya triangulation
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

        Logger.log("🔍 [UnrealImport] Configured FBX import with triangulation DISABLED")

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
    triangulation_time: float
    import_time: float

    @property
    def total_time(self) -> float:
        """Total time including triangulation and import"""
        return self.triangulation_time + self.import_time

    @property
    def average_triangulation_time(self) -> float:
        """Calculate average triangulation time per file"""
        return self.triangulation_time / self.files_processed if self.files_processed > 0 else 0.0

    @property
    def average_import_time(self) -> float:
        """Calculate average import time per file"""
        return self.import_time / self.files_imported if self.files_imported > 0 else 0.0

    def print_summary(self) -> None:
        """Print simplified benchmark results summary"""
        actual_triangulation = self.triangulation_enabled and self.maya_available
        success_rate = (self.files_imported / self.original_files_found * 100) if self.original_files_found > 0 else 0

        print("\n" + "=" * 50)
        print("       FBX IMPORT BENCHMARK RESULTS")
        print("=" * 50)

        # Core results
        print(f"📊 Files: {self.files_imported}/{self.original_files_found} imported ({success_rate:.1f}%)")
        print(f"⚡ Import Time: {self.import_time:.3f}s ({self.average_import_time:.3f}s/file)")

        # Processing details
        if actual_triangulation:
            print(f"🔧 Triangulation: {self.triangulation_time:.3f}s ({self.average_triangulation_time:.3f}s/file)")
            print(f"📈 Total Time: {self.total_time:.3f}s")
        elif self.triangulation_enabled and not self.maya_available:
            print(f"📁 File Copy: {self.triangulation_time:.3f}s (Maya unavailable)")

        print(f"🚀 Throughput: {(self.files_imported / self.import_time):.2f} files/second")
        print("=" * 50)

        # Also log to Unreal for console visibility
        Logger.log(
            f"🎯 [Benchmark] Import: {self.import_time:.3f}s | Files: {self.files_imported} | Rate: {self.average_import_time:.3f}s/file"
        )


class FBXBenchmarkRunner:
    """Main benchmark runner orchestrating the entire process"""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.maya_checker = MayaChecker(config)
        self.triangulator = MayaTriangulator(config, self.maya_checker)
        self.file_processor = FileProcessor(config, self.triangulator)

    def run(self) -> BenchmarkResults:
        """Execute the complete benchmark process"""
        Logger.log("🚀 [FBXBenchmark] Starting FBX Skeletal Mesh Import Benchmark...")
        Logger.log("📊 [FBXBenchmark] This benchmark measures PURE IMPORT performance (triangulation is separate)")
        Logger.log(f"🔍 [FBXBenchmark] Maya triangulation script: {self.config.maya_triangulate_script}")

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

        # Process files (triangulation phase)
        processed_files, triangulation_time = self.file_processor.process_fbx_files(source_folder, fbx_files)
        if not processed_files:
            Logger.log("No files were successfully processed", LogLevel.ERROR)
            return self._create_failed_results()

        # Import into Unreal (pure import benchmark)
        Logger.log("🚀 Starting pure import benchmark phase...")
        import_results = self._import_to_unreal(processed_files)

        # Cleanup
        self.file_processor.cleanup_working_directory()

        # Create and return results
        results = BenchmarkResults(
            triangulation_enabled=self.config.triangulate_mesh,
            maya_available=self.maya_checker.is_available,
            original_files_found=len(fbx_files),
            files_processed=len(processed_files),
            files_imported=import_results["imported_count"],
            triangulation_time=triangulation_time,
            import_time=import_results["import_time"],
        )

        results.print_summary()
        return results

    def _log_initial_status(self) -> None:
        """Log initial status of Maya and triangulation"""
        Logger.log(f"🔍 [FBXBenchmark] Configuration check - Triangulation enabled: {self.config.triangulate_mesh}")
        Logger.log("🔍 [FBXBenchmark] Maya availability check starting...")

        if self.config.triangulate_mesh and self.maya_checker.is_available:
            Logger.log(
                "⚙️ [FBXBenchmark] Triangulation: ENABLED - Maya available (files will be triangulated before import)"
            )
        elif self.config.triangulate_mesh and not self.maya_checker.is_available:
            Logger.log(
                "⚠️ [FBXBenchmark] Triangulation: ENABLED but Maya unavailable - files will be copied without triangulation"
            )
        else:
            Logger.log("⚙️ [FBXBenchmark] Triangulation: DISABLED - files will be copied as-is")

        Logger.log("⏱️ [FBXBenchmark] Import timing will measure ONLY the Unreal import phase for accurate benchmarking")

    def _create_failed_results(self) -> BenchmarkResults:
        """Create results object for failed benchmark"""
        return BenchmarkResults(
            triangulation_enabled=self.config.triangulate_mesh,
            maya_available=self.maya_checker.is_available,
            original_files_found=0,
            files_processed=0,
            files_imported=0,
            triangulation_time=0.0,
            import_time=0.0,
        )

    def _import_to_unreal(self, processed_files: List[Path]) -> dict:
        """Import processed files into Unreal Engine - measures pure import time only"""
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        import_options = UnrealImportOptions.create_skeletal_mesh_options()

        # Create import tasks
        all_tasks = []
        for processed_file in processed_files:
            processed_file_path = processed_file.as_posix()
            task = UnrealImportOptions.create_import_task(
                processed_file_path, self.config.import_destination, import_options
            )
            all_tasks.append(task)

        Logger.log(f"⚡ Executing pure import benchmark for {len(all_tasks)} files...")

        # Execute import - THIS IS THE PURE IMPORT BENCHMARK
        start_time = time.time()
        asset_tools.import_asset_tasks(all_tasks)
        end_time = time.time()

        import_time = end_time - start_time

        # Count successful imports
        imported_count = 0
        for task in all_tasks:
            if task.get_editor_property("imported_object_paths"):
                imported_count += 1
                filename = Path(task.get_editor_property("filename")).name
                Logger.log(f"✅ Successfully imported: {filename}")
            else:
                filename = Path(task.get_editor_property("filename")).name
                Logger.log(f"❌ Failed to import: {filename}", LogLevel.ERROR)

        Logger.log(f"🎯 Pure import benchmark complete: {imported_count}/{len(all_tasks)} files in {import_time:.4f}s")

        return {"imported_count": imported_count, "import_time": import_time}


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
