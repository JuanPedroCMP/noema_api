
import subprocess
import sys
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
MAX_WORKERS = 40
IDLE_TIMEOUT = 30
REQUIREMENTS_FILE = Path("requirements.txt")

print_lock = threading.Lock()


def log(message):
    with print_lock:
        print(message, flush=True)


def install_package(package):
    log(f"[START] {package}")

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--progress-bar", "off",
        package
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        last_activity = time.monotonic()
        output = []

        while True:
            line = process.stdout.readline()

            if line:
                output.append(line)
                last_activity = time.monotonic()

            elif process.poll() is not None:
                break

            elif time.monotonic() - last_activity > IDLE_TIMEOUT:
                process.kill()
                process.wait()

                return package, False, "Idle timeout (10 seconds)"

            else:
                time.sleep(0.1)

        if process.returncode == 0:
            return package, True, "Installed successfully"

        return package, False, "".join(output)[-1000:]

    except Exception as error:
        return package, False, str(error)


def main():
    if not REQUIREMENTS_FILE.exists():
        print("requirements.txt not found!")
        return

    with REQUIREMENTS_FILE.open(encoding="utf-8") as file:
        packages = [
            line.strip()
            for line in file
            if line.strip() and not line.strip().startswith("#")
        ]

    successful = []
    failed = []

    print(f"\nTotal packages: {len(packages)}")
    print(f"Concurrent installations: {MAX_WORKERS}")
    print(f"Idle timeout: {IDLE_TIMEOUT}s\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(install_package, package)
            for package in packages
        ]

        for future in as_completed(futures):
            package, success, message = future.result()

            if success:
                successful.append(package)
                log(f"[SUCCESS] {package}")
            else:
                failed.append((package, message))
                log(f"[FAILED] {package}: {message}")

    print("\n" + "=" * 50)
    print("INSTALLATION SUMMARY")
    print("=" * 50)

    print(f"Total:      {len(packages)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed:     {len(failed)}")

    if failed:
        print("\nFailed packages:")
        for package, reason in failed:
            print(f"\n- {package}")
            print(f"  Reason: {reason}")

    print("\nFinished!")


if __name__ == "__main__":
    main()
