"""
Maya Mesh Optimization Benchmark Script

This script benchmarks mesh optimization for animation caches by simulating
the complete AYON animation pipeline including FBX export performance.

Usage:
1. Run this script in Maya's Script Editor
2. Select a rig or character set in the outliner
3. Click "Run Benchmark" to test optimization performance
"""

import os
import time
from functools import wraps

from maya import cmds, mel


def timing_decorator(func):
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        execution_time = end_time - start_time
        return result, execution_time
    return wrapper


class MockLogger:
    """Simple logger for output."""
    def info(self, msg): print(f"INFO: {msg}")
    def warning(self, msg): print(f"WARNING: {msg}")
    def error(self, msg): print(f"ERROR: {msg}")
    def debug(self, msg): print(f"DEBUG: {msg}")


class MeshOptimizer:
    """Handles mesh optimization logic matching AYON plugins."""

    def __init__(self):
        self.log = MockLogger()

    def get_meshes_from_selection(self, selection):
        """Get all mesh shapes from selected objects (simulating AYON's out_SET approach)."""
        if not selection:
            return []

        # Simulate AYON's approach: look for sets ending with out_SET or controls_SET
        sets_found = []
        for sel in selection:
            if sel.endswith("out_SET") or sel.endswith("controls_SET"):
                sets_found.append(sel)

        # If no sets found, treat selection as root objects
        if not sets_found:
            roots = selection
        else:
            # Get members from the sets
            roots = []
            for set_node in sets_found:
                if cmds.objExists(set_node) and cmds.nodeType(set_node) == "objectSet":
                    members = cmds.sets(set_node, query=True) or []
                    roots.extend(members)
                else:
                    roots.append(set_node)

        # Get all descendants from roots
        all_nodes = []
        for root in roots:
            if cmds.objExists(root):
                descendants = cmds.listRelatives(root, allDescendents=True, fullPath=True)
                if descendants:
                    all_nodes.extend(descendants)
                all_nodes.append(root)

        # Get mesh shapes only (non-intermediate)
        meshes = cmds.ls(all_nodes, type="mesh", long=True, noIntermediate=True)
        return list(set(meshes if meshes else []))

    def create_blank_mesh(self):
        """Create a blank mesh with minimal geometry (matching AYON plugin)."""
        plane = cmds.polyPlane(
            name="optimization_blank_mesh",
            width=1, height=1, subdivisionsX=1, subdivisionsY=1,
            constructionHistory=False
        )[0]

        shapes = cmds.listRelatives(plane, shapes=True, fullPath=True)
        if not shapes:
            raise RuntimeError("Failed to create blank mesh")

        mesh_shape = shapes[0]
        cmds.setAttr(f"{plane}.visibility", 0)
        return mesh_shape

    def optimize_mesh(self, mesh, blank_mesh):
        """Replace mesh data with blank mesh (matching AYON plugin)."""
        in_mesh_plug = f"{mesh}.inMesh"

        # Store original connection
        original_connection = None
        connections = cmds.listConnections(in_mesh_plug, source=True, destination=False, plugs=True)

        if connections:
            original_connection = {
                "source": connections[0],
                "destination": in_mesh_plug,
            }

        # Connect blank mesh
        try:
            cmds.connectAttr(f"{blank_mesh}.outMesh", in_mesh_plug, force=True)
            return original_connection
        except Exception as e:
            self.log.error(f"Failed to connect blank mesh to {mesh}: {e}")
            return None

    def optimize_meshes(self, meshes):
        """Optimize all provided meshes using single blank mesh."""
        if not meshes:
            self.log.warning("No meshes to optimize")
            return {}

        # Create ONE blank mesh for ALL optimizations (like AYON plugin)
        blank_mesh = self.create_blank_mesh()
        optimization_data = {
            "blank_mesh": blank_mesh,
            "mesh_connections": {},
        }

        # Connect same blank mesh to ALL target meshes
        for mesh in meshes:
            try:
                original_connection = self.optimize_mesh(mesh, blank_mesh)
                optimization_data["mesh_connections"][mesh] = original_connection
                self.log.debug(f"Optimized mesh: {mesh}")
            except Exception as e:
                self.log.warning(f"Failed to optimize mesh {mesh}: {e}")

        self.log.info(f"Optimized {len(optimization_data['mesh_connections'])} meshes")
        return optimization_data

    def restore_meshes(self, optimization_data):
        """Restore original mesh connections (matching AYON plugin)."""
        if not optimization_data:
            self.log.debug("No optimization data to restore")
            return

        mesh_connections = optimization_data.get("mesh_connections", {})
        restored_count = 0

        for mesh, original_connection in mesh_connections.items():
            try:
                if not cmds.objExists(mesh):
                    self.log.warning(f"Mesh {mesh} no longer exists")
                    continue

                if original_connection:
                    # Restore original connection
                    source = original_connection["source"]
                    destination = original_connection["destination"]
                    if cmds.objExists(source.split(".")[0]):
                        cmds.connectAttr(source, destination, force=True)
                        self.log.debug(f"Restored: {source} -> {destination}")
                    else:
                        self.log.warning(f"Original source {source} no longer exists")
                else:
                    # Disconnect blank mesh
                    try:
                        cmds.disconnectAttr(
                            f"{optimization_data['blank_mesh']}.outMesh",
                            f"{mesh}.inMesh"
                        )
                        self.log.debug(f"Disconnected blank mesh from {mesh}")
                    except:
                        pass  # Already disconnected

                restored_count += 1
            except Exception as e:
                self.log.error(f"Failed to restore mesh {mesh}: {e}")

        # Clean up blank mesh
        blank_mesh = optimization_data.get("blank_mesh")
        if blank_mesh and cmds.objExists(blank_mesh):
            try:
                transform = cmds.listRelatives(blank_mesh, parent=True, fullPath=True)
                if transform:
                    cmds.delete(transform[0])
                    self.log.debug("Deleted blank mesh")
            except Exception as e:
                self.log.warning(f"Failed to delete blank mesh: {e}")

        self.log.info(f"Restored {restored_count} mesh connections")


class MeshOptimizationBenchmark:
    """Main benchmark class for testing AYON animation pipeline performance."""

    def __init__(self):
        self.optimizer = MeshOptimizer()
        self.results = {}

    def get_mesh_stats(self, meshes):
        """Get mesh statistics."""
        if not meshes:
            return {"count": 0, "total_vertices": 0, "total_faces": 0}

        total_vertices = 0
        total_faces = 0

        for mesh in meshes:
            if cmds.objExists(mesh):
                try:
                    vertices = cmds.polyEvaluate(mesh, vertex=True)
                    faces = cmds.polyEvaluate(mesh, face=True)
                    total_vertices += vertices or 0
                    total_faces += faces or 0
                except:
                    pass

        return {
            "count": len(meshes),
            "total_vertices": total_vertices,
            "total_faces": total_faces
        }

    @timing_decorator
    def mesh_evaluation_test(self, meshes):
        """Test mesh evaluation performance."""
        operations = 0
        for mesh in meshes:
            if cmds.objExists(mesh):
                try:
                    # Simulate cache extraction operations
                    cmds.polyEvaluate(mesh, vertex=True)
                    cmds.polyEvaluate(mesh, face=True)
                    cmds.getAttr(f"{mesh}.worldMesh[0]")
                    operations += 3
                except:
                    pass
        return operations

    @timing_decorator
    def deformer_evaluation_test(self, meshes):
        """Test deformer evaluation performance."""
        deformer_ops = 0
        for mesh in meshes:
            if cmds.objExists(mesh):
                try:
                    # Find deformers
                    history = cmds.listHistory(mesh, pruneDagObjects=True)
                    if history:
                        deformers = cmds.ls(history, type=["skinCluster", "blendShape", "cluster", "ffd"])
                        if deformers:
                            # Trigger deformer evaluation
                            cmds.getAttr(f"{mesh}.worldMesh[0]")
                            deformer_ops += len(deformers)
                except:
                    pass
        return deformer_ops

    @timing_decorator
    def fbx_export_test(self, meshes, keep_file=True, file_suffix=""):
        """Test FBX export performance - THE KEY OPERATION that benefits from optimization."""
        try:
            # Find transform objects with meshes for export
            export_objects = set()
            for mesh in meshes:
                if cmds.objExists(mesh):
                    transforms = cmds.listRelatives(mesh, parent=True, fullPath=True)
                    if transforms:
                        export_objects.update(transforms)

            if not export_objects:
                return {"size": 0, "path": None}

            # Get hierarchy roots for export (simulating extract_fbx_animation.py)
            export_roots = []
            for obj in export_objects:
                # Find top-level parent
                current = obj
                while True:
                    parents = cmds.listRelatives(current, parent=True, fullPath=True)
                    if not parents:
                        export_roots.append(current)
                        break
                    current = parents[0]

            # Remove duplicates and limit to reasonable size
            export_roots = list(set(export_roots))[:5]

            if not export_roots:
                return {"size": len(meshes), "path": None}

            # Setup FBX export
            if keep_file:
                temp_fbx = f"benchmark_animation_export{file_suffix}.fbx"
            else:
                temp_fbx = "benchmark_animation_temp.fbx"

            # Load FBX plugin if needed
            if not cmds.pluginInfo("fbxmaya", query=True, loaded=True):
                try:
                    cmds.loadPlugin("fbxmaya")
                except:
                    print("FBX plugin not available, skipping FBX export test")
                    return {"size": len(meshes), "path": None}

            # Select objects for export
            cmds.select(export_roots, replace=True)

            # Configure FBX export settings (matching extract_fbx_animation.py workflow)
            mel.eval('FBXResetExport')
            mel.eval('FBXExportSmoothingGroups -v true')
            mel.eval('FBXExportHardEdges -v false')
            mel.eval('FBXExportTangents -v false')
            mel.eval('FBXExportSmoothMesh -v true')
            mel.eval('FBXExportInstances -v false')
            mel.eval('FBXExportReferencedAssetsContent -v true')
            mel.eval('FBXExportAnimationOnly -v false')
            mel.eval('FBXExportBakeComplexAnimation -v false')
            mel.eval('FBXExportUseSceneName -v false')
            mel.eval('FBXExportQuaternion -v euler')
            mel.eval('FBXExportShapes -v true')
            mel.eval('FBXExportSkins -v true')
            mel.eval('FBXExportConstraints -v false')
            mel.eval('FBXExportCameras -v false')
            mel.eval('FBXExportLights -v false')

            # Export FBX (this is where optimization makes the biggest difference)
            mel.eval(f'FBXExport -f "{temp_fbx}" -s')

            # Get file size and path
            file_size = 0
            file_path = None
            if os.path.exists(temp_fbx):
                file_size = os.path.getsize(temp_fbx)
                file_path = os.path.abspath(temp_fbx)
                
                if not keep_file:
                    try:
                        os.remove(temp_fbx)
                        file_path = None
                    except:
                        pass

            return {"size": file_size, "path": file_path}

        except Exception as e:
            print(f"FBX export test failed: {e}")
            return {"size": 0, "path": None}

    @timing_decorator
    def scene_save_test(self):
        """Test Maya scene save performance."""
        try:
            current_file = cmds.file(query=True, sceneName=True)
            temp_file = current_file.replace(".ma", "_benchmark_temp.ma") if current_file else "benchmark_temp.ma"

            cmds.file(rename=temp_file)
            cmds.file(save=True, type="mayaAscii")

            file_size = 0
            if os.path.exists(temp_file):
                file_size = os.path.getsize(temp_file)
                try:
                    os.remove(temp_file)
                except:
                    pass

            return file_size
        except Exception as e:
            print(f"Scene save test failed: {e}")
            return 0

    def run_benchmark(self, selected_objects=None):
        """Run the complete AYON animation pipeline benchmark."""
        print("\n" + "="*80)
        print("AYON ANIMATION PIPELINE BENCHMARK")
        print("Testing mesh optimization impact on FBX export workflow")
        print("="*80)

        # Get selection
        if not selected_objects:
            selected_objects = cmds.ls(selection=True, long=True)

        if not selected_objects:
            print("ERROR: No objects selected. Please select a rig or character set.")
            return None

        print(f"Selected objects: {[obj.split('|')[-1] for obj in selected_objects]}")

        # Get meshes using AYON-style discovery
        meshes = self.optimizer.get_meshes_from_selection(selected_objects)
        mesh_stats = self.get_mesh_stats(meshes)

        print(f"\nFound {mesh_stats['count']} meshes in hierarchy:")
        print(f"  Total vertices: {mesh_stats['total_vertices']:,}")
        print(f"  Total faces: {mesh_stats['total_faces']:,}")

        if not meshes:
            print("No meshes found. Please select objects containing mesh geometry.")
            return None

        # === BEFORE OPTIMIZATION (Original Pipeline) ===
        print("\n" + "-"*50)
        print("BEFORE OPTIMIZATION (Original Pipeline)")
        print("-"*50)

        mesh_ops, mesh_time = self.mesh_evaluation_test(meshes)
        print(f"Mesh evaluation: {mesh_time:.4f}s ({mesh_ops} operations)")

        deformer_ops, deformer_time = self.deformer_evaluation_test(meshes)
        print(f"Deformer evaluation: {deformer_time:.4f}s ({deformer_ops} deformer operations)")

        # THE KEY TEST: FBX Export Performance
        fbx_result, fbx_time = self.fbx_export_test(meshes, keep_file=False)
        fbx_size = fbx_result["size"]
        print(f"🎯 FBX EXPORT: {fbx_time:.4f}s (size: {fbx_size:,} bytes) - KEY METRIC")

        scene_size, scene_time = self.scene_save_test()
        print(f"Scene save: {scene_time:.4f}s (size: {scene_size:,} bytes)")

        # === OPTIMIZATION PHASE ===
        print("\n" + "-"*50)
        print("RUNNING MESH OPTIMIZATION")
        print("-"*50)
        opt_start = time.time()
        optimization_data = self.optimizer.optimize_meshes(meshes)
        opt_time = time.time() - opt_start
        print(f"Optimization completed in {opt_time:.4f}s")
        print(f"Replaced {len(optimization_data.get('mesh_connections', {}))} meshes with single blank mesh")

        # === AFTER OPTIMIZATION (Optimized Pipeline) ===
        print("\n" + "-"*50)
        print("AFTER OPTIMIZATION (Optimized Pipeline)")
        print("-"*50)

        mesh_ops_opt, mesh_time_opt = self.mesh_evaluation_test(meshes)
        print(f"Mesh evaluation: {mesh_time_opt:.4f}s ({mesh_ops_opt} operations)")

        deformer_ops_opt, deformer_time_opt = self.deformer_evaluation_test(meshes)
        print(f"Deformer evaluation: {deformer_time_opt:.4f}s ({deformer_ops_opt} operations)")

        # THE KEY TEST: Optimized FBX Export Performance
        fbx_result_opt, fbx_time_opt = self.fbx_export_test(meshes, keep_file=False)
        fbx_size_opt = fbx_result_opt["size"]
        print(f"🎯 FBX EXPORT: {fbx_time_opt:.4f}s (size: {fbx_size_opt:,} bytes) - KEY METRIC")

        scene_size_opt, scene_time_opt = self.scene_save_test()
        print(f"Scene save: {scene_time_opt:.4f}s (size: {scene_size_opt:,} bytes)")

        # === RESTORATION PHASE ===
        print("\n" + "-"*50)
        print("RUNNING MESH RESTORATION")
        print("-"*50)
        restore_start = time.time()
        self.optimizer.restore_meshes(optimization_data)
        restore_time = time.time() - restore_start
        print(f"Restoration completed in {restore_time:.4f}s")

        # === FINAL FBX EXPORT FOR USER ===
        print("\n" + "-"*50)
        print("CREATING FINAL FBX EXPORT FOR USER")
        print("-"*50)
        
        # Export final FBX with optimized settings for user to import
        final_fbx_result, final_fbx_time = self.fbx_export_test(meshes, file_suffix="_final")
        final_fbx_path = final_fbx_result["path"]
        final_fbx_size = final_fbx_result["size"]
        
        if final_fbx_path:
            print(f"✅ Final FBX exported in {final_fbx_time:.4f}s")
            print(f"📁 FBX File: {final_fbx_path}")
            print(f"📦 File Size: {final_fbx_size:,} bytes")
        else:
            print("❌ Failed to create final FBX export")

        # === PERFORMANCE RESULTS ===
        print("\n" + "="*80)
        print("🚀 PERFORMANCE IMPROVEMENT RESULTS")
        print("="*80)

        # Calculate speedups
        mesh_speedup = mesh_time / mesh_time_opt if mesh_time_opt > 0 else float('inf')
        deformer_speedup = deformer_time / deformer_time_opt if deformer_time_opt > 0 else float('inf')
        fbx_speedup = fbx_time / fbx_time_opt if fbx_time_opt > 0 else float('inf')
        scene_speedup = scene_time / scene_time_opt if scene_time_opt > 0 else float('inf')

        # File size reductions
        fbx_reduction = ((fbx_size - fbx_size_opt) / fbx_size * 100) if fbx_size > 0 else 0
        scene_reduction = ((scene_size - scene_size_opt) / scene_size * 100) if scene_size > 0 else 0

        print("Mesh Operations:")
        print(f"  Before: {mesh_time:.4f}s")
        print(f"  After:  {mesh_time_opt:.4f}s")
        print(f"  Speedup: {mesh_speedup:.2f}x ({((mesh_speedup-1)*100):.1f}% faster)")

        print("\nDeformer Operations:")
        print(f"  Before: {deformer_time:.4f}s")
        print(f"  After:  {deformer_time_opt:.4f}s")
        print(f"  Speedup: {deformer_speedup:.2f}x ({((deformer_speedup-1)*100):.1f}% faster)")

        print("\n🎯 FBX EXPORT (Most Important):")
        print(f"  Before: {fbx_time:.4f}s ({fbx_size:,} bytes)")
        print(f"  After:  {fbx_time_opt:.4f}s ({fbx_size_opt:,} bytes)")
        print(f"  Speedup: {fbx_speedup:.2f}x ({((fbx_speedup-1)*100):.1f}% faster)")
        print(f"  File size reduction: {fbx_reduction:.1f}%")

        print("\nScene Save:")
        print(f"  Before: {scene_time:.4f}s ({scene_size:,} bytes)")
        print(f"  After:  {scene_time_opt:.4f}s ({scene_size_opt:,} bytes)")
        print(f"  Speedup: {scene_speedup:.2f}x ({((scene_speedup-1)*100):.1f}% faster)")
        print(f"  File size reduction: {scene_reduction:.1f}%")

        # Overall pipeline assessment
        total_before = mesh_time + deformer_time + fbx_time + scene_time
        total_after = mesh_time_opt + deformer_time_opt + fbx_time_opt + scene_time_opt
        overall_speedup = total_before / total_after if total_after > 0 else float('inf')
        overhead_time = opt_time + restore_time
        net_speedup = total_before / (total_after + overhead_time) if (total_after + overhead_time) > 0 else float('inf')

        print("\n📊 OVERALL PIPELINE PERFORMANCE:")
        print(f"  Total time before optimization: {total_before:.4f}s")
        print(f"  Total time after optimization:  {total_after:.4f}s")
        print(f"  Raw speedup: {overall_speedup:.2f}x ({((overall_speedup-1)*100):.1f}% faster)")
        print(f"  Optimization overhead: {opt_time:.4f}s")
        print(f"  Restoration overhead: {restore_time:.4f}s")
        print(f"  Net speedup (including overhead): {net_speedup:.2f}x")

        # Assessment
        if fbx_speedup > 2.0:
            assessment = "🟢 EXCELLENT - Significant performance improvement!"
        elif fbx_speedup > 1.5:
            assessment = "🟡 GOOD - Noticeable performance improvement"
        elif fbx_speedup > 1.1:
            assessment = "🟠 MINOR - Small performance improvement"
        else:
            assessment = "🔴 MINIMAL - Limited benefit from optimization"

        print(f"\n🎖️  ASSESSMENT: {assessment}")
        print(f"FBX export is the key bottleneck - {fbx_speedup:.2f}x speedup achieved")

        # === FBX FILE FOR IMPORT ===
        if final_fbx_path:
            print("\n" + "="*80)
            print("📦 FBX FILE READY FOR IMPORT")
            print("="*80)
            print(f"📁 Path: {final_fbx_path}")
            print(f"📦 Size: {final_fbx_size:,} bytes")
            print(f"⏱️  Export Time: {final_fbx_time:.4f}s")
            print("\n💡 You can now import this FBX file into any 3D application!")
            print("   The file contains your optimized animation data.")

        # Store results
        self.results = {
            "mesh_count": mesh_stats["count"],
            "vertex_count": mesh_stats["total_vertices"],
            "face_count": mesh_stats["total_faces"],
            "fbx_speedup": fbx_speedup,
            "fbx_size_reduction": fbx_reduction,
            "overall_speedup": overall_speedup,
            "net_speedup": net_speedup,
            "optimization_time": opt_time,
            "restoration_time": restore_time,
            "final_fbx_path": final_fbx_path,
            "final_fbx_size": final_fbx_size
        }

        print("\n" + "="*80)
        return self.results


def create_benchmark_ui():
    """Create AYON animation pipeline benchmark UI."""
    window_name = "ayonAnimationBenchmark"

    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    window = cmds.window(window_name, title="AYON Animation Pipeline Benchmark", widthHeight=(500, 400))

    cmds.columnLayout(adjustableColumn=True, columnOffset=['both', 15])

    cmds.text(label="AYON Animation Pipeline Benchmark", height=35,
              backgroundColor=[0.2, 0.4, 0.6], font="boldLabelFont")
    cmds.separator(height=15)

    cmds.text(label="🎯 Tests mesh optimization impact on FBX export performance",
              align="center", font="obliqueLabelFont")
    cmds.separator(height=10)

    cmds.text(label="Instructions:", align="left", font="boldLabelFont")
    cmds.text(label="1. Select a rigged character or animation hierarchy", align="left")
    cmds.text(label="2. Click 'Run Animation Pipeline Benchmark'", align="left")
    cmds.text(label="3. Check Script Editor for detailed FBX export results", align="left")
    cmds.separator(height=15)

    cmds.text(label="Current Selection:", align="left", font="boldLabelFont")
    selection_text = cmds.text(label="None", align="left", backgroundColor=[0.15, 0.15, 0.15], height=25)

    def update_selection():
        selected = cmds.ls(selection=True)
        if selected:
            display_names = [obj.split('|')[-1] for obj in selected[:3]]
            if len(selected) > 3:
                display_names.append(f"... and {len(selected)-3} more")
            cmds.text(selection_text, edit=True,
                     label=f"{len(selected)} objects: {', '.join(display_names)}")
        else:
            cmds.text(selection_text, edit=True, label="None selected")

    cmds.button(label="Refresh Selection", command=lambda x: update_selection(), height=30)
    cmds.separator(height=15)

    def run_benchmark_ui():
        try:
            benchmark = MeshOptimizationBenchmark()
            results = benchmark.run_benchmark()

            if results:
                fbx_speedup = results.get('fbx_speedup', 1.0)
                size_reduction = results.get('fbx_size_reduction', 0.0)
                final_fbx_path = results.get('final_fbx_path', '')
                
                # Create message with FBX path info
                fbx_info = ""
                if final_fbx_path:
                    fbx_filename = os.path.basename(final_fbx_path)
                    fbx_info = f"\n📁 FBX Created: {fbx_filename}\n📍 Ready for import!"

                message = f"""🚀 AYON Animation Pipeline Benchmark Complete!

Meshes tested: {results['mesh_count']} ({results['vertex_count']:,} vertices)
🎯 FBX Export Speedup: {fbx_speedup:.2f}x
📦 FBX Size Reduction: {size_reduction:.1f}%
⚡ Overall Pipeline Speedup: {results['overall_speedup']:.2f}x{fbx_info}

This shows the real-world performance improvement
animators will experience during cache publishing!

See Script Editor for complete detailed analysis."""

                cmds.confirmDialog(title="🎖️ Benchmark Results", message=message, button=["Excellent!"])
            else:
                cmds.confirmDialog(title="❌ Benchmark Failed",
                                 message="Please select a rigged character with mesh geometry.",
                                 button=["OK"])
        except Exception as e:
            cmds.confirmDialog(title="💥 Error", message=f"Benchmark error: {str(e)}", button=["OK"])

    cmds.button(label="🚀 Run Animation Pipeline Benchmark", height=50,
                backgroundColor=[0.3, 0.7, 0.3], command=lambda x: run_benchmark_ui())

    cmds.separator(height=15)
    cmds.text(label="🎬 Simulates complete AYON animation workflow:",
              align="center", font="boldLabelFont")
    cmds.text(label="OptimizeAnimationMeshes → FBX Export → RestoreAnimationMeshes",
              align="center", font="smallPlainLabelFont")

    update_selection()
    cmds.showWindow(window)


# Auto-run
if __name__ == "__main__":
    print("🎬 AYON Animation Pipeline Benchmark loaded!")
    print("This benchmark tests the real performance impact on FBX export workflows")
    create_benchmark_ui()