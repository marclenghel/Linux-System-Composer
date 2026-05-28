use sysinfo::System;
use std::process::Command;

// ── STRUCTS ───────────────────────────────────────────────────────────────────

// A struct is a blueprint. Think of it like a form with named fields.
// Once defined, you can create as many filled-in copies as you want.

struct HardwareReport {
    os: String,           // text, like "Linux" or "macOS"
    kernel: String,       // text, like "6.9.3-arch1"
    cpu: String,          // text, like "Intel Core i7-1165G7"
    total_ram_gb: f64,    // decimal number, like 15.87
    disks: Vec<String>,   // a list of text items, one per disk
}

struct GpuInfo {
    vendor: String,   // "NVIDIA", "AMD", "Intel", "Apple"
    name: String,     // "GeForce RTX 3060", "Radeon RX 6700", etc.
}

// ── OS DETECTION ──────────────────────────────────────────────────────────────

// std::env::consts::OS is a built-in Rust constant set at compile time.
// It contains the OS name as a string: "linux", "macos", or "windows".
// These three functions just make the rest of the code easier to read.

fn is_mac() -> bool {
    std::env::consts::OS == "macos"
}

fn is_windows() -> bool {
    std::env::consts::OS == "windows"
}

fn is_linux() -> bool {
    std::env::consts::OS == "linux"
}

// ── PACKAGE MANAGER DETECTION (Linux only) ────────────────────────────────────

// On Linux, every distro has a different package manager.
// We check which one exists by trying to run each one.
// command_exists() runs a command with --version and checks if it succeeded.

fn command_exists(cmd: &str) -> bool {
    // Command::new() creates a command to run
    // .arg() adds an argument to it
    // .output() runs it and captures the result
    // .map() transforms the Ok value — here we check if exit code was 0
    // .unwrap_or(false) handles the Err case — if the command wasn't found at all
    Command::new(cmd)
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

// This tries to install pciutils using whatever package manager exists.
// It returns true if installation succeeded, false if it failed.
// &[&str] means a slice (a list) of string references — we pass the full command as pieces.
// For example: &["pacman", "-S", "--noconfirm", "pciutils"]

fn try_install_pciutils() -> bool {
    // Each branch checks for a package manager and runs the install command.
    // sudo is prepended because package installation needs admin rights.
    // .args() takes all the pieces and passes them as separate arguments.
    // .status() runs the command and returns just the exit code (we don't need the output).

    if command_exists("pacman") {
        // Arch Linux, Manjaro, CachyOS, EndeavourOS...
        println!("Detected pacman — installing pciutils via pacman...");
        Command::new("sudo")
            .args(["pacman", "-S", "--noconfirm", "pciutils"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)

    } else if command_exists("apt-get") {
        // Debian, Ubuntu, Linux Mint, Pop!_OS...
        println!("Detected apt-get — installing pciutils via apt...");
        Command::new("sudo")
            .args(["apt-get", "install", "-y", "pciutils"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)

    } else if command_exists("dnf") {
        // Fedora, RHEL 8+, CentOS Stream...
        println!("Detected dnf — installing pciutils via dnf...");
        Command::new("sudo")
            .args(["dnf", "install", "-y", "pciutils"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)

    } else if command_exists("zypper") {
        // openSUSE, SUSE Linux Enterprise...
        println!("Detected zypper — installing pciutils via zypper...");
        Command::new("sudo")
            .args(["zypper", "install", "-y", "pciutils"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)

    } else if command_exists("xbps-install") {
        // Void Linux...
        println!("Detected xbps — installing pciutils via xbps...");
        Command::new("sudo")
            .args(["xbps-install", "-y", "pciutils"])
            .status()
            .map(|s| s.success())
            .unwrap_or(false)

    } else {
        // No known package manager found — tell the user what to do manually
        println!("Could not detect a package manager.");
        println!("Please install pciutils manually:");
        println!("  Arch:    sudo pacman -S pciutils");
        println!("  Debian:  sudo apt install pciutils");
        println!("  Fedora:  sudo dnf install pciutils");
        println!("  openSUSE: sudo zypper install pciutils");
        false
    }
}

// This is the main entry point for pciutils management.
// It checks if lspci exists, and if not, tries to install it.
// Returns true if lspci is available (either it was already there, or we installed it).
// Returns false if we couldn't get it.

fn ensure_lspci() -> bool {
    // First check: does lspci already exist?
    if command_exists("lspci") {
        return true; // already installed, nothing to do
    }

    // Not found — tell the user and try to install
    println!("lspci not found. Attempting to install pciutils automatically...");

    let success = try_install_pciutils();

    if success {
        println!("pciutils installed successfully.");
        // Double-check it actually works now
        command_exists("lspci")
    } else {
        println!("Automatic installation failed.");
        println!("Try running this program with sudo, or install pciutils manually.");
        false
    }
}

// ── HARDWARE REPORT ───────────────────────────────────────────────────────────

// This uses the sysinfo crate to get basic system info.
// sysinfo works on Linux, macOS, and Windows — so this function needs no OS branching.

fn detect() -> HardwareReport {
    // System::new_all() creates the detection object
    // refresh_all() populates it with current data
    let mut sys = System::new_all();
    sys.refresh_all();

    // .cpus() returns a list of all CPU cores
    // .first() gets the first one, returning Option<&Cpu>
    // .map(|c| ...) transforms the Some value — extracts the brand name
    // .unwrap_or(...) provides a fallback if the list was empty
    let cpu = sys.cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or("Unknown".to_string());

    // Disks::new_with_refreshed_list() gets all disks right now
    // .iter() lets us loop through them
    // .map() transforms each disk into its name as a String
    // .to_string_lossy() handles non-UTF8 path characters safely
    // .collect() gathers all the transformed values into a Vec<String>
    let disks = sysinfo::Disks::new_with_refreshed_list()
        .iter()
        .map(|d| d.name().to_string_lossy().to_string())
        .collect();

    HardwareReport {
        os:           System::name().unwrap_or("Unknown".to_string()),
        kernel:       System::kernel_version().unwrap_or("Unknown".to_string()),
        cpu,
        total_ram_gb: sys.total_memory() as f64 / 1_073_741_824.0,
        disks,
    }
}

// ── MAC CHIP DETECTION ────────────────────────────────────────────────────────

// system_profiler is a macOS command that outputs detailed hardware info.
// SPHardwareDataType = the hardware section specifically.
// Output looks like:
//
//   Hardware Overview:
//     Model Name: MacBook Pro
//     Chip: Apple M3 Pro          ← Apple Silicon
//     Processor Name: Intel ...   ← Intel Mac (older)

fn detect_mac_chip() -> String {
    let output = Command::new("system_profiler")
        .arg("SPHardwareDataType")
        .output();

    if let Ok(o) = output {
        let text = String::from_utf8_lossy(&o.stdout);

        for line in text.lines() {
            let lower = line.to_lowercase();

            if lower.contains("chip:") || lower.contains("processor name:") {
                // Find the ':' and take everything after it
                if let Some(colon_pos) = line.find(':') {
                    let chip_name = line[colon_pos + 1..].trim().to_string();
                    if !chip_name.is_empty() {
                        return chip_name;
                    }
                }
            }
        }
    }

    // Fallback for Intel Macs
    let fallback = Command::new("sysctl")
        .args(["-n", "machdep.cpu.brand_string"])
        .output();

    match fallback {
        Ok(o) => {
            let result = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if result.is_empty() { "Unknown Apple chip".to_string() } else { result }
        }
        Err(_) => "Unknown Apple chip".to_string(),
    }
}

// ── GPU DETECTION — MAC ───────────────────────────────────────────────────────

// system_profiler SPDisplaysDataType = the GPU/display section.
// Output looks like:
//
//   Graphics/Displays:
//     Apple M3 Pro:
//       Chipset Model: Apple M3 Pro   ← this is the line we want
//       Type: GPU
//       Vendor: Apple (0x106b)
//
// We scan every line looking for "Chipset Model:" and extract the value after the colon.

fn detect_gpus_mac() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    let output = Command::new("system_profiler")
        .arg("SPDisplaysDataType")
        .output();

    let output = match output {
        Ok(o) => o,
        Err(_) => {
            println!("system_profiler not found.");
            return gpus;
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        let lower = line.to_lowercase();

        if lower.contains("chipset model:") {
            if let Some(colon_pos) = line.find(':') {
                let name = line[colon_pos + 1..].trim().to_string();

                let vendor = if lower.contains("apple") {
                    "Apple"
                } else if lower.contains("nvidia") {
                    "NVIDIA"
                } else if lower.contains("amd") || lower.contains("radeon") {
                    "AMD"
                } else if lower.contains("intel") {
                    "Intel"
                } else {
                    "Unknown"
                };

                gpus.push(GpuInfo {
                    vendor: vendor.to_string(),
                    name,
                });
            }
        }
    }

    gpus
}

// ── GPU DETECTION — WINDOWS ───────────────────────────────────────────────────

// Windows doesn't have lspci or system_profiler.
// Instead, Windows has WMI (Windows Management Instrumentation) — a system database
// that stores hardware info. You can query it using PowerShell.
//
// The PowerShell command we run:
//   powershell -Command "Get-WmiObject Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | Format-List"
//
// Output looks like:
//   Name         : NVIDIA GeForce RTX 3060
//   AdapterRAM   : 12884901888
//   DriverVersion: 31.0.15.3623
//
//   Name         : Intel(R) UHD Graphics 770
//   AdapterRAM   : 1073741824
//   DriverVersion: 31.0.101.2125
//
// We parse this line by line, building a GpuInfo for each GPU we find.

fn detect_gpus_windows() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    // Run PowerShell and capture its output
    // -Command tells PowerShell to run a command string directly
    let output = Command::new("powershell")
        .args([
            "-NoProfile",     // don't load user profile — faster startup
            "-Command",
            // Get-WmiObject queries Windows hardware database
            // Win32_VideoController is the GPU table
            // Select-Object picks which columns we want
            // Format-List prints one property per line (easier to parse)
            "Get-WmiObject Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion | Format-List"
        ])
        .output();

    let output = match output {
        Ok(o) => o,
        Err(_) => {
            println!("PowerShell not found — cannot detect GPU on Windows.");
            return gpus;
        }
    };

    // PowerShell output is UTF-16 on some systems but usually UTF-8 in modern Windows
    // from_utf8_lossy handles any encoding issues safely
    let text = String::from_utf8_lossy(&output.stdout);

    // We build up one GpuInfo at a time as we scan lines.
    // Option<T> means "either Some(value) or None"
    // We start with None and fill in values as we find them.
    let mut current_name: Option<String> = None;
    let mut current_driver: Option<String> = None;

    for line in text.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("Name") && trimmed.contains(':') {
            // Found a new GPU name — if we already had one being built, save it first
            // This handles multiple GPUs in the output
            if let Some(name) = current_name.take() {
                // .take() extracts the value and replaces it with None
                let vendor = detect_vendor_from_name(&name);
                gpus.push(GpuInfo { vendor, name });
                current_driver = None;
            }

            // Now start building the new one
            if let Some(colon_pos) = trimmed.find(':') {
                let name = trimmed[colon_pos + 1..].trim().to_string();
                if !name.is_empty() {
                    current_name = Some(name);
                }
            }

        } else if trimmed.starts_with("DriverVersion") && trimmed.contains(':') {
            // Save the driver version for potential future use
            if let Some(colon_pos) = trimmed.find(':') {
                current_driver = Some(trimmed[colon_pos + 1..].trim().to_string());
            }
        }
    }

    // After the loop, save the last GPU being built (the loop ends before saving it)
    if let Some(name) = current_name {
        let vendor = detect_vendor_from_name(&name);
        gpus.push(GpuInfo { vendor, name });
        let _ = current_driver; // silence unused warning for now
    }

    gpus
}

// ── GPU DETECTION — LINUX ─────────────────────────────────────────────────────

// lspci lists all PCI devices. GPUs connect via PCI so they show up here.
// Output looks like:
//   01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)
//
// We filter lines that mention VGA, display, or 3D controller.
// Then extract the vendor and model name from each matching line.

fn detect_gpus_linux() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    // First make sure lspci is available — install it if not
    if !ensure_lspci() {
        return gpus;
    }

    let output = match Command::new("lspci").output() {
        Ok(o) => o,
        Err(_) => {
            println!("Failed to run lspci even after installation check.");
            return gpus;
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        let lower = line.to_lowercase();

        // Check if this line describes a GPU
        let is_gpu = lower.contains("vga compatible")
            || lower.contains("display controller")
            || lower.contains("3d controller");

        if !is_gpu {
            continue; // skip non-GPU lines
        }

        // A line looks like: "01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)"
        // splitn(3, ':') splits at ':' but stops at 3 pieces:
        //   piece 0: "01"
        //   piece 1: "00.0 VGA compatible controller"
        //   piece 2: " NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)"
        // .nth(2) gets piece 2. .trim() removes surrounding whitespace.
        let after_colon = line
            .splitn(3, ':')
            .nth(2)
            .unwrap_or(line)
            .trim();

        let vendor = detect_vendor_from_name(after_colon);

        // Extract model from inside [brackets]
        // We search for ']' only AFTER '[' to prevent the begin > end panic
        let model = if let Some(start) = after_colon.find('[') {
            let after_bracket = &after_colon[start + 1..]; // everything after '['
            if let Some(end) = after_bracket.find(']') {
                after_bracket[..end].to_string() // everything before ']'
            } else {
                after_bracket.to_string()
            }
        } else {
            after_colon.to_string() // no brackets — use the whole name
        };

        gpus.push(GpuInfo { vendor, name: model });
    }

    gpus
}

// ── SHARED VENDOR DETECTION ───────────────────────────────────────────────────

// All three platforms need to figure out the vendor from a device name string.
// Instead of copy-pasting this logic three times, we put it in one function.
// &str means we borrow the string — we just read it, we don't own it.
// -> String means we return a new owned String.

fn detect_vendor_from_name(name: &str) -> String {
    let lower = name.to_lowercase();

    if lower.contains("nvidia") {
        "NVIDIA".to_string()
    } else if lower.contains("amd")
        || lower.contains("advanced micro")
        || lower.contains("radeon") {
        "AMD".to_string()
    } else if lower.contains("intel") {
        "Intel".to_string()
    } else if lower.contains("apple") {
        "Apple".to_string()
    } else {
        "Unknown".to_string()
    }
}

// ── GPU ROUTER ────────────────────────────────────────────────────────────────

// This is the only GPU function that main() calls.
// It picks the right detection method based on which OS we're on.
// The pattern "if ... else if ... else" returns a Vec<GpuInfo> in all branches.

fn detect_gpus() -> Vec<GpuInfo> {
    if is_mac() {
        detect_gpus_mac()
    } else if is_windows() {
        detect_gpus_windows()
    } else {
        detect_gpus_linux() // also the fallback for any other Unix
    }
}

// ── MAIN ──────────────────────────────────────────────────────────────────────

// main() is the entry point — Rust always starts here.
// It calls our detection functions and prints the results.
// Notice it doesn't know or care which OS it's on —
// all the OS-specific logic is hidden inside the functions above.

fn main() {
    let report = detect();

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("      Hardware Report");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    println!("OS:         {}", report.os);
    println!("Kernel:     {}", report.kernel);

    // Only show the chip line on Mac — it's redundant on other platforms
    if is_mac() {
        println!("Chip:       {}", detect_mac_chip());
    } else if is_windows() {
        println!("CPU:        {}", report.cpu);
    } else if is_linux() {
        println!("CPU:        {}", report.cpu);
    }
    println!("RAM:        {:.2} GB", report.total_ram_gb);
    // {:.2} means format as decimal with 2 digits after the point: 15.87

    println!("Disks:");
    for disk in &report.disks {
        // &report.disks borrows the list — we read it without taking ownership
        println!("   - {}", disk);
    }

    println!("GPU:");
    let gpus = detect_gpus();
    if gpus.is_empty() {
        println!("   None detected");
    } else {
        for gpu in &gpus {
            println!("   Vendor: {}", gpu.vendor);
            println!("   Model:  {}", gpu.name);
        }
    }

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
}