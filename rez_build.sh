# Build all the rez packages in the current directory
build_all_rez() {
    local success=0
    local fail=0
    local total=0
    local start_time
    local end_time
    local elapsed

    echo "Starting rez build in all subdirectories of: $(pwd)"
    for d in */; do
        if [ -d "$d" ]; then
            total=$((total + 1))
            echo "=================================================="
            echo "[$total] Entering directory: $d"
            start_time=$(date +%s)
            if cd "$d"; then
                echo "Running: rez-build -ci"
                if rez-build -ci; then
                    echo "+++ SUCCESS in $d +++"
                    success=$((success + 1))
                else
                    echo "--- FAILED in $d ---"
                    fail=$((fail + 1))
                fi
                cd ..
            else
                echo "--- FAILED to enter directory $d ---"
                fail=$((fail + 1))
            fi
            end_time=$(date +%s)
            elapsed=$((end_time - start_time))
            echo "Time taken in $d: ${elapsed}s"
        fi
    done
    echo "=================================================="
    echo "Rez build summary:"
    echo "  Total directories: $total"
    echo "  Successful builds: $success"
    echo "  Failed builds:     $fail"
    if [ "$fail" -eq 0 ]; then
        echo "All builds completed successfully! 🎉"
    else
        echo "Some builds failed. Please check the logs above."
    fi
}