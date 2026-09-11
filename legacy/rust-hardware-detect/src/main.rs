// ┌─────────────────────────────────────────────────────────────────┐
// │  Linux System Composer — Hardware Detector                      │
// │  Detects: OS, Kernel, CPU, RAM, Motherboard, Disks,            │
// │           GPU, Drivers, Network Cards                           │
// │  Platforms: Linux (/proc + /sys + ip), macOS (system_profiler  │
// │             + networksetup + kextstat), Windows (WMI/PowerShell)│
// │  Output: human-readable text + hardware_report.json            │
// └─────────────────────────────────────────────────────────────────┘

use serde::Serialize;    // lets us convert structs → JSON automatically
use sysinfo::System;     // cross-platform CPU, RAM, Disk baseline
use std::process::Command;
use std::fs;
use std::collections::HashSet;

// ── STRUCTS ───────────────────────────────────────────────────────────────────
//
// #[derive(Serialize)] is a "macro" — it auto-generates code that lets
// serde_json convert the struct to JSON. Without it, you'd write that
// conversion by hand for every struct.
//
// #[derive(Debug)] lets you print the struct with {:?} for debugging.
// Together they go on one line: #[derive(Serialize, Debug)]

#[derive(Serialize, Debug)]
struct HardwareReport {
    os:            String,
    kernel:        String,
    cpu:           CpuInfo,
    ram:           RamInfo,
    motherboard:   String,
    disks:         Vec<DiskInfo>,
    gpus:          Vec<GpuInfo>,
    drivers:       Vec<DriverInfo>,
    network_cards: Vec<NetworkCard>,
}

// Nested struct for CPU — a field can be another struct, not just a primitive
#[derive(Serialize, Debug)]
struct CpuInfo {
    brand: String,   // "AMD Ryzen 9 7950X" or "Apple M3 Pro"
    cores: usize,    // logical cores (usize = the size of a pointer, used for counts)
    arch:  String,   // "x86_64", "aarch64", etc.
}

#[derive(Serialize, Debug)]
struct RamInfo {
    total_gb: f64,   // f64 = 64-bit decimal number
}

#[derive(Serialize, Debug)]
struct DiskInfo {
    name:      String,
    size_gb:   f64,
    disk_type: String,   // "SSD", "HDD", "NVMe", "Unknown"
}

#[derive(Serialize, Debug)]
struct GpuInfo {
    vendor: String,
    name:   String,
}

// DriverInfo comes from:
//   Linux:   /proc/modules  — status is "Live", "Loading", or "Unloading"
//   macOS:   kextstat       — status is "Loaded"
//   Windows: Win32_SystemDriver via PowerShell — status is "Running", "Stopped", etc.
#[derive(Serialize, Debug)]
struct DriverInfo {
    name:   String,
    status: String,
}

#[derive(Serialize, Debug)]
struct NetworkCard {
    name:        String,
    mac_address: String,
}

// ── OS DETECTION ──────────────────────────────────────────────────────────────
//
// std::env::consts::OS is a &str constant set at COMPILE time.
// It equals "linux", "macos", or "windows" depending on where you compile.
// These helper functions just make the if-chains below more readable.

fn is_mac()     -> bool { std::env::consts::OS == "macos"   }
fn is_windows() -> bool { std::env::consts::OS == "windows" }

// ── UTILITY FUNCTIONS ─────────────────────────────────────────────────────────

// Checks if a program exists by running it with --version.
// Returns true if it ran successfully (exit code 0), false otherwise.
// &str = borrowed string reference — we read the value, we don't own it.
fn command_exists(cmd: &str) -> bool {
    Command::new(cmd)
        .arg("--version")
        .output()
        .map(|o| o.status.success())   // transform Ok(output) → Ok(true/false)
        .unwrap_or(false)              // if Err (command not found), return false
}

// Runs a command and returns its stdout as a String, or None if it failed.
// &[&str] = a slice of string references (a list of arguments).
fn run(cmd: &str, args: &[&str]) -> Option<String> {
    Command::new(cmd)
        .args(args)
        .output()
        .ok()                          // convert Result → Option (Err becomes None)
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
}

// ── PCIUTILS MANAGEMENT (Linux GPU detection dependency) ──────────────────────

// Tries to install pciutils using whichever package manager exists on this Linux distro.
// The table in the project notes shows lspci + /sys for Linux GPU detection.
fn try_install_pciutils() -> bool {
    // Each branch:
    //   1. checks if that package manager exists
    //   2. runs the install with sudo
    //   3. returns true if it succeeded

    if command_exists("pacman") {
        // Arch, Manjaro, CachyOS, EndeavourOS, Garuda...
        println!("  → Detected pacman, installing via pacman...");
        Command::new("sudo").args(["pacman", "-S", "--noconfirm", "pciutils"])
            .status().map(|s| s.success()).unwrap_or(false)

    } else if command_exists("apt-get") {
        // Debian, Ubuntu, Mint, Pop!_OS...
        println!("  → Detected apt-get, installing via apt...");
        Command::new("sudo").args(["apt-get", "install", "-y", "pciutils"])
            .status().map(|s| s.success()).unwrap_or(false)

    } else if command_exists("dnf") {
        // Fedora, RHEL 8+, CentOS Stream...
        println!("  → Detected dnf, installing via dnf...");
        Command::new("sudo").args(["dnf", "install", "-y", "pciutils"])
            .status().map(|s| s.success()).unwrap_or(false)

    } else if command_exists("zypper") {
        // openSUSE, SUSE Linux Enterprise...
        println!("  → Detected zypper, installing via zypper...");
        Command::new("sudo").args(["zypper", "install", "-y", "pciutils"])
            .status().map(|s| s.success()).unwrap_or(false)

    } else if command_exists("xbps-install") {
        // Void Linux...
        println!("  → Detected xbps, installing via xbps...");
        Command::new("sudo").args(["xbps-install", "-y", "pciutils"])
            .status().map(|s| s.success()).unwrap_or(false)

    } else {
        println!("  → No known package manager found. Install pciutils manually:");
        println!("     Arch:    sudo pacman -S pciutils");
        println!("     Debian:  sudo apt install pciutils");
        println!("     Fedora:  sudo dnf install pciutils");
        false
    }
}

// Ensures lspci is available. Installs it if missing.
// Returns true if lspci is ready to use.
fn ensure_lspci() -> bool {
    if command_exists("lspci") { return true; }

    println!("lspci not found — attempting auto-install...");
    let ok = try_install_pciutils();
    if ok {
        println!("  → Installed successfully.");
        command_exists("lspci")   // verify it actually works
    } else {
        println!("  → Auto-install failed. Run with sudo or install manually.");
        false
    }
}

// ── KERNEL DETECTION ──────────────────────────────────────────────────────────
//
// Source per platform (from project data table):
//   Linux:   uname -r  → "6.9.3-arch1-1"
//   macOS:   uname -r  → "23.4.0" (Darwin kernel version)
//   Windows: WMI Win32_OperatingSystem via PowerShell

fn detect_kernel() -> String {
    if is_windows() {
        run("powershell", &[
            "-NoProfile", "-Command",
            "(Get-WmiObject Win32_OperatingSystem).Version"
        ]).unwrap_or("Unknown".to_string())
    } else {
        // uname -r works on both Linux and macOS
        run("uname", &["-r"]).unwrap_or("Unknown".to_string())
    }
}

// ── CPU + RAM DETECTION ───────────────────────────────────────────────────────
//
// sysinfo abstracts the platform differences:
//   Linux:   reads /proc/cpuinfo and /proc/meminfo
//   macOS:   calls sysctl
//   Windows: calls Win32 API (GlobalMemoryStatusEx, etc.)
//
// We create System once and use it for both to avoid double-initialization.

fn detect_cpu_and_ram() -> (CpuInfo, RamInfo) {
    // System::new_all() creates the sysinfo object
    // refresh_all() populates it with current live data
    let mut sys = System::new_all();
    sys.refresh_all();

    // .cpus() → Vec of logical CPU cores
    // .first() → Option<&Cpu> — the first core (all share the same brand name)
    // .map(|c| ...) → transform the Some value
    // .unwrap_or(...) → fallback if the list was empty
    let brand = sys.cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or("Unknown".to_string());

    let cpu = CpuInfo {
        brand,
        cores: sys.cpus().len(),
        // std::env::consts::ARCH is set at compile time: "x86_64", "aarch64", etc.
        arch: std::env::consts::ARCH.to_string(),
    };

    // sys.total_memory() returns bytes (u64)
    // Divide by 1_073_741_824 (= 1024³) to get GiB
    // as f64 converts the integer to a decimal so the division gives 15.87 not 15
    let ram = RamInfo {
        total_gb: sys.total_memory() as f64 / 1_073_741_824.0,
    };

    (cpu, ram)
}

// ── MOTHERBOARD DETECTION ─────────────────────────────────────────────────────
//
// Source per platform (from project data table):
//   Linux:   /sys/class/dmi/id/board_vendor + board_name  (no sudo needed!)
//   macOS:   system_profiler SPHardwareDataType (returns model name)
//   Windows: Win32_BaseBoard via PowerShell

fn detect_motherboard() -> String {
    if is_mac()     { detect_motherboard_mac()     }
    else if is_windows() { detect_motherboard_windows() }
    else            { detect_motherboard_linux()   }
}

fn detect_motherboard_linux() -> String {
    // /sys/class/dmi/id/ exposes BIOS/DMI data as plain text files.
    // No sudo required — readable by any user.
    // This is the source behind `dmidecode` but without needing root.

    let vendor = fs::read_to_string("/sys/class/dmi/id/board_vendor")
        .unwrap_or_default().trim().to_string();

    let name = fs::read_to_string("/sys/class/dmi/id/board_name")
        .unwrap_or_default().trim().to_string();

    // format! works like println! but produces a String instead of printing
    if vendor.is_empty() && name.is_empty() {
        "Unknown".to_string()
    } else {
        format!("{} {}", vendor, name).trim().to_string()
    }
}

fn detect_motherboard_mac() -> String {
    // Macs don't have a separate motherboard in the traditional sense.
    // system_profiler SPHardwareDataType gives us the Mac model instead.
    // We look for "Model Name:" or "Model Identifier:" in the output.
    let output = Command::new("system_profiler")
        .arg("SPHardwareDataType").output();

    if let Ok(o) = output {
        let text = String::from_utf8_lossy(&o.stdout);
        for line in text.lines() {
            let lower = line.to_lowercase();
            if lower.contains("model name:") || lower.contains("model identifier:") {
                if let Some(colon) = line.find(':') {
                    let val = line[colon + 1..].trim().to_string();
                    if !val.is_empty() { return val; }
                }
            }
        }
    }
    "Apple Mac (model unknown)".to_string()
}

fn detect_motherboard_windows() -> String {
    // Win32_BaseBoard contains motherboard info in Windows' hardware database
    run("powershell", &[
        "-NoProfile", "-Command",
        "Get-WmiObject Win32_BaseBoard | \
         Select-Object Manufacturer,Product | Format-List"
    ])
    .map(|text| {
        // Parse "Manufacturer : ASUSTeK\nProduct : ROG HERO" → "ASUSTeK ROG HERO"
        let mut mfr = String::new();
        let mut prod = String::new();
        for line in text.lines() {
            if line.to_lowercase().starts_with("manufacturer") {
                if let Some(c) = line.find(':') {
                    mfr = line[c+1..].trim().to_string();
                }
            } else if line.to_lowercase().starts_with("product") {
                if let Some(c) = line.find(':') {
                    prod = line[c+1..].trim().to_string();
                }
            }
        }
        format!("{} {}", mfr, prod).trim().to_string()
    })
    .unwrap_or("Unknown".to_string())
}

// ── DISK DETECTION ────────────────────────────────────────────────────────────
//
// Source per platform (from project data table):
//   Linux:   /sys/block (via sysinfo which reads it internally) + NVMe detection
//   macOS:   diskutil (via sysinfo)
//   Windows: DeviceIoControl (via sysinfo)
//
// sysinfo wraps all three natively. We add NVMe name detection on top.

fn detect_disks() -> Vec<DiskInfo> {
    let disk_list = sysinfo::Disks::new_with_refreshed_list();

    // HashSet is like a Vec but automatically removes duplicates.
    // We use it to avoid showing the same physical disk multiple times
    // (sysinfo can return /dev/sda1, /dev/sda2, etc. — we want /dev/sda).
    let mut seen: HashSet<String> = HashSet::new();
    let mut disks = Vec::new();

    for disk in disk_list.iter() {
        let name = disk.name().to_string_lossy().to_string();

        // .insert() returns false if the item was already in the set
        if !seen.insert(name.clone()) { continue; }

        let size_gb = disk.total_space() as f64 / 1_000_000_000.0;
        if size_gb < 0.1 { continue; }  // skip tiny/virtual disks

        // sysinfo.kind() reads /sys/block/X/queue/rotational on Linux:
        //   0 = non-rotational (SSD) → DiskKind::SSD
        //   1 = rotational (HDD)     → DiskKind::HDD
        let disk_type = match disk.kind() {
            sysinfo::DiskKind::HDD => "HDD".to_string(),
            sysinfo::DiskKind::SSD => {
                // Refine: if the name contains "nvme", it's NVMe not just SSD
                if name.to_lowercase().contains("nvme") {
                    "NVMe".to_string()
                } else {
                    "SSD".to_string()
                }
            }
            _ => "Unknown".to_string(),
        };

        disks.push(DiskInfo { name, size_gb, disk_type });
    }

    disks
}

// ── GPU VENDOR HELPER ─────────────────────────────────────────────────────────
//
// All three GPU detection functions need to identify the vendor from a name string.
// Instead of copying this logic three times, it lives here once.
// &str = borrow the string (read-only), -> String = return an owned String

fn detect_vendor_from_name(name: &str) -> String {
    let lower = name.to_lowercase();
    if      lower.contains("nvidia")                              { "NVIDIA".to_string() }
    else if lower.contains("amd") || lower.contains("radeon")
         || lower.contains("advanced micro")                      { "AMD".to_string()    }
    else if lower.contains("intel")                              { "Intel".to_string()  }
    else if lower.contains("apple")                              { "Apple".to_string()  }
    else                                                          { "Unknown".to_string()}
}

// ── GPU DETECTION — LINUX ─────────────────────────────────────────────────────
//
// Source from table: lspci + /sys
// lspci lists PCI devices. GPUs appear as "VGA compatible controller",
// "Display controller", or "3D controller".
// Example output:
//   01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)

fn detect_gpus_linux() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();
    if !ensure_lspci() { return gpus; }

    let output = match Command::new("lspci").output() {
        Ok(o) => o,
        Err(_) => return gpus,
    };

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        let lower = line.to_lowercase();
        let is_gpu = lower.contains("vga compatible")
            || lower.contains("display controller")
            || lower.contains("3d controller");

        if !is_gpu { continue; }

        // Split "01:00.0 VGA compatible controller: NVIDIA ... [RTX 3060] (rev a1)"
        // at ':' into max 3 pieces. Piece [2] = " NVIDIA Corporation ... (rev a1)"
        let after_colon = line.splitn(3, ':').nth(2).unwrap_or(line).trim();
        let vendor = detect_vendor_from_name(after_colon);

        // Extract model from [brackets].
        // Search for ']' AFTER '[' to prevent the begin > end panic
        // (if we searched the whole string, ']' might appear before '[')
        let model = if let Some(start) = after_colon.find('[') {
            let after_bracket = &after_colon[start + 1..];
            if let Some(end) = after_bracket.find(']') {
                after_bracket[..end].to_string()
            } else {
                after_bracket.to_string()
            }
        } else {
            after_colon.to_string()
        };

        gpus.push(GpuInfo { vendor, name: model });
    }
    gpus
}

// ── GPU DETECTION — MAC ───────────────────────────────────────────────────────
//
// Source from table: system_profiler
// system_profiler SPDisplaysDataType shows GPU info.
// We look for "Chipset Model:" lines.

fn detect_gpus_mac() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    let output = match Command::new("system_profiler")
        .arg("SPDisplaysDataType").output()
    {
        Ok(o) => o,
        Err(_) => { println!("system_profiler not found."); return gpus; }
    };

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        if line.to_lowercase().contains("chipset model:") {
            if let Some(colon) = line.find(':') {
                let name = line[colon + 1..].trim().to_string();
                let vendor = detect_vendor_from_name(&name);
                gpus.push(GpuInfo { vendor, name });
            }
        }
    }
    gpus
}

// ── GPU DETECTION — WINDOWS ───────────────────────────────────────────────────
//
// Source from table: WMI / DXGI
// We use Win32_VideoController via PowerShell — same underlying data as DXGI
// Output per GPU:
//   Name         : NVIDIA GeForce RTX 3060
//   AdapterRAM   : 12884901888
//   DriverVersion: 31.0.15.3623

fn detect_gpus_windows() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    let text = match run("powershell", &[
        "-NoProfile", "-Command",
        "Get-WmiObject Win32_VideoController | \
         Select-Object Name,AdapterRAM,DriverVersion | Format-List"
    ]) {
        Some(t) => t,
        None => { println!("PowerShell not found."); return gpus; }
    };

    // We build one GpuInfo per GPU block as we scan lines.
    // Option<String> = either Some(name) while building, or None when idle.
    let mut current_name: Option<String> = None;

    for line in text.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("Name") && trimmed.contains(':') {
            // Save the previous GPU before starting a new one
            if let Some(name) = current_name.take() {
                // .take() extracts the value AND sets it back to None in one step
                gpus.push(GpuInfo { vendor: detect_vendor_from_name(&name), name });
            }
            if let Some(c) = trimmed.find(':') {
                let name = trimmed[c + 1..].trim().to_string();
                if !name.is_empty() { current_name = Some(name); }
            }
        }
    }
    // Save the last GPU (the loop ends before the final save)
    if let Some(name) = current_name {
        gpus.push(GpuInfo { vendor: detect_vendor_from_name(&name), name });
    }

    gpus
}

// ── GPU ROUTER ────────────────────────────────────────────────────────────────

fn detect_gpus() -> Vec<GpuInfo> {
    if is_mac()     { detect_gpus_mac()     }
    else if is_windows() { detect_gpus_windows() }
    else            { detect_gpus_linux()   }
}

// ── DRIVER DETECTION ──────────────────────────────────────────────────────────
//
// Source per platform (from project data table):
//   Linux:   /proc/modules  — lists all loaded kernel modules
//   macOS:   kextstat       — lists loaded kernel extensions
//   Windows: Win32_SystemDriver via PowerShell (= DriverQuery equivalent)

fn detect_drivers() -> Vec<DriverInfo> {
    if is_mac()          { detect_drivers_mac()     }
    else if is_windows() { detect_drivers_windows() }
    else                 { detect_drivers_linux()   }
}

fn detect_drivers_linux() -> Vec<DriverInfo> {
    // /proc/modules lists every currently loaded kernel module (driver).
    // fs::read_to_string reads the whole file as a String.
    // Format: module_name  size  use_count  used_by  status  address  [flags]
    // Example:
    //   nvidia 56352768 59 nvidia_modeset,nvidia_uvm, Live 0x0000000000000000 (POE)
    //   bluetooth 806912 34 btusb,btrtl, Live 0x0000000000000000

    let content = match fs::read_to_string("/proc/modules") {
        Ok(c) => c,
        Err(e) => {
            println!("Cannot read /proc/modules: {}", e);
            return Vec::new();
        }
    };

    let mut drivers = Vec::new();

    for line in content.lines() {
        // split_whitespace() splits on any whitespace and ignores multiple spaces
        let parts: Vec<&str> = line.split_whitespace().collect();

        // We need at least 5 fields to get the status column
        if parts.len() >= 5 {
            drivers.push(DriverInfo {
                name:   parts[0].to_string(), // module name
                status: parts[4].to_string(), // "Live", "Loading", or "Unloading"
            });
        }
    }

    drivers
}

fn detect_drivers_mac() -> Vec<DriverInfo> {
    // kextstat lists loaded kernel extensions on macOS.
    // Output: Index Refs Address Size Wired Name (Version) <Linked Against>
    // Name is at column index 5 (0-based).
    //
    // Note: kextstat is deprecated on macOS 12+ (Monterey) where Apple
    // moved to System Extensions. We try it anyway and handle gracefully.

    let output = match Command::new("kextstat").output() {
        Ok(o) => o,
        Err(_) => {
            println!("kextstat not available on this macOS version.");
            return Vec::new();
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);
    let mut drivers = Vec::new();

    // skip(1) skips the header line
    for line in text.lines().skip(1) {
        let parts: Vec<&str> = line.split_whitespace().collect();
        // Column 5 = kext name like "com.apple.kpi.bsd"
        if let Some(name) = parts.get(5) {
            drivers.push(DriverInfo {
                name:   name.to_string(),
                status: "Loaded".to_string(),
            });
        }
    }

    drivers
}

fn detect_drivers_windows() -> Vec<DriverInfo> {
    // Win32_SystemDriver = Windows kernel drivers (equivalent to DriverQuery)
    // We get Name and State for each driver.
    // State values: "Running", "Stopped", "Start Pending", etc.

    let text = match run("powershell", &[
        "-NoProfile", "-Command",
        "Get-WmiObject Win32_SystemDriver | \
         Select-Object Name,State | Format-List"
    ]) {
        Some(t) => t,
        None => return Vec::new(),
    };

    let mut drivers = Vec::new();
    let mut current_name: Option<String> = None;

    for line in text.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("Name") && trimmed.contains(':') {
            if let Some(c) = trimmed.find(':') {
                current_name = Some(trimmed[c + 1..].trim().to_string());
            }
        } else if trimmed.starts_with("State") && trimmed.contains(':') {
            if let Some(name) = current_name.take() {
                let status = trimmed.find(':')
                    .map(|c| trimmed[c + 1..].trim().to_string())
                    .unwrap_or("Unknown".to_string());
                if !name.is_empty() {
                    drivers.push(DriverInfo { name, status });
                }
            }
        }
    }

    drivers
}

// ── NETWORK CARD DETECTION ────────────────────────────────────────────────────
//
// Source per platform (from project data table):
//   Linux:   ip link + /sys — `ip link show` lists interfaces with MACs
//   macOS:   networksetup   — `networksetup -listallhardwareports`
//   Windows: GetAdaptersInfo (via Win32_NetworkAdapter in PowerShell)

fn detect_network() -> Vec<NetworkCard> {
    if is_mac()          { detect_network_mac()     }
    else if is_windows() { detect_network_windows() }
    else                 { detect_network_linux()   }
}

fn detect_network_linux() -> Vec<NetworkCard> {
    // `ip link show` output:
    //   1: lo: <LOOPBACK,...>          ← loopback — skip
    //       link/loopback 00:00:...
    //   2: enp3s0: <BROADCAST,...>     ← real card — keep
    //       link/ether aa:bb:cc:dd:ee:ff brd ...
    //   3: wlo1: <BROADCAST,...>       ← wifi — keep
    //       link/ether 11:22:33:44:55:66 brd ...

    let output = match Command::new("ip").args(["link", "show"]).output() {
        Ok(o) => o,
        Err(_) => { println!("ip command not found."); return Vec::new(); }
    };

    let text = String::from_utf8_lossy(&output.stdout);
    let mut cards = Vec::new();
    let mut current_name: Option<String> = None;

    for line in text.lines() {
        // Interface header lines start with a digit: "2: enp3s0: <..."
        let first_char = line.chars().next();
        if first_char.map(|c| c.is_ascii_digit()).unwrap_or(false) {
            // splitn(3, ':') → ["2", " enp3s0", " <BROADCAST,...>"]
            let parts: Vec<&str> = line.splitn(3, ':').collect();
            if parts.len() >= 2 {
                let name = parts[1].trim().to_string();
                // "lo" is the loopback interface — not a real network card
                current_name = if name == "lo" { None } else { Some(name) };
            }

        } else if line.trim().starts_with("link/ether") {
            // MAC address line: "    link/ether aa:bb:cc:dd:ee:ff brd ..."
            // .take() extracts Some(name) AND resets current_name to None
            if let Some(name) = current_name.take() {
                let parts: Vec<&str> = line.split_whitespace().collect();
                let mac = parts.get(1).unwrap_or(&"Unknown").to_string();
                cards.push(NetworkCard { name, mac_address: mac });
            }
        }
    }

    cards
}

fn detect_network_mac() -> Vec<NetworkCard> {
    // `networksetup -listallhardwareports` output:
    //   Hardware Port: Wi-Fi
    //   Device: en0
    //   Ethernet Address: a4:c3:f0:12:34:56
    //
    //   Hardware Port: Bluetooth PAN
    //   Device: en6
    //   Ethernet Address: (null)    ← skip empty ones

    let output = match Command::new("networksetup")
        .arg("-listallhardwareports").output()
    {
        Ok(o) => o,
        Err(_) => { println!("networksetup not found."); return Vec::new(); }
    };

    let text = String::from_utf8_lossy(&output.stdout);
    let mut cards = Vec::new();
    let mut current_device: Option<String> = None;

    for line in text.lines() {
        let lower = line.to_lowercase();

        if lower.starts_with("device:") {
            if let Some(c) = line.find(':') {
                current_device = Some(line[c + 1..].trim().to_string());
            }

        } else if lower.starts_with("ethernet address:") {
            if let Some(device) = current_device.take() {
                // find(':') returns the position of the first ':'
                // In "Ethernet Address: aa:bb:cc:dd:ee:ff" that's after "Ethernet Address"
                // So line[pos+1..] = " aa:bb:cc:dd:ee:ff" → trimmed = "aa:bb:cc:dd:ee:ff"
                if let Some(c) = line.find(':') {
                    let mac = line[c + 1..].trim().to_string();
                    // Skip null/empty MACs — some virtual interfaces have none
                    if !mac.is_empty() && mac != "(null)" {
                        cards.push(NetworkCard { name: device, mac_address: mac });
                    }
                }
            }
        }
    }

    cards
}

fn detect_network_windows() -> Vec<NetworkCard> {
    // Win32_NetworkAdapter with PhysicalAdapter=true filters out virtual adapters
    // Output per adapter:
    //   Name       : Intel Wi-Fi 6 AX200
    //   MACAddress : AA:BB:CC:DD:EE:FF

    let text = match run("powershell", &[
        "-NoProfile", "-Command",
        "Get-WmiObject Win32_NetworkAdapter | \
         Where-Object {$_.PhysicalAdapter} | \
         Select-Object Name,MACAddress | Format-List"
    ]) {
        Some(t) => t,
        None => return Vec::new(),
    };

    let mut cards = Vec::new();
    let mut current_name: Option<String> = None;

    for line in text.lines() {
        let trimmed = line.trim();

        if trimmed.starts_with("Name") && trimmed.contains(':') {
            if let Some(c) = trimmed.find(':') {
                current_name = Some(trimmed[c + 1..].trim().to_string());
            }
        } else if trimmed.starts_with("MACAddress") && trimmed.contains(':') {
            if let Some(name) = current_name.take() {
                // MACAddress field itself contains colons — take everything after first ':'
                // "MACAddress : AA:BB:CC:DD:EE:FF"
                //               ↑ first ':'
                if let Some(c) = trimmed.find(':') {
                    let mac = trimmed[c + 1..].trim().to_string();
                    if !mac.is_empty() {
                        cards.push(NetworkCard { name, mac_address: mac });
                    }
                }
            }
        }
    }

    cards
}

// ── ASSEMBLE FULL REPORT ──────────────────────────────────────────────────────
//
// This function calls every detection function and combines the results
// into a single HardwareReport struct ready for printing or JSON export.

fn detect() -> HardwareReport {
    // We detect CPU and RAM together to create System only once
    let (cpu, ram) = detect_cpu_and_ram();

    HardwareReport {
        os:            System::name().unwrap_or("Unknown".to_string()),
        kernel:        detect_kernel(),
        cpu,
        ram,
        motherboard:   detect_motherboard(),
        disks:         detect_disks(),
        gpus:          detect_gpus(),
        drivers:       detect_drivers(),
        network_cards: detect_network(),
    }
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
//
// Entry point. Detects everything, prints a human-readable text report,
// then serializes the full report to JSON and saves it to hardware_report.json.
// The JSON is structured for Linux System Composer to consume for
// compatibility checking and component recommendations.

fn main() {
    println!("Detecting hardware...\n");

    let report = detect();

    // ── Text Report ───────────────────────────────────────────────────────────

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  Hardware Report");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("OS:           {}", report.os);
    println!("Kernel:       {}", report.kernel);
    println!("CPU:          {} ({} cores, {})",
        report.cpu.brand, report.cpu.cores, report.cpu.arch);
    println!("RAM:          {:.2} GB", report.ram.total_gb);
    println!("Motherboard:  {}", report.motherboard);

    println!("\nDisks:");
    if report.disks.is_empty() {
        println!("  None detected");
    } else {
        for d in &report.disks {
            println!("  {} — {:.1} GB  [{}]", d.name, d.size_gb, d.disk_type);
        }
    }

    println!("\nGPU:");
    if report.gpus.is_empty() {
        println!("  None detected");
    } else {
        for g in &report.gpus {
            println!("  {} — {}", g.vendor, g.name);
        }
    }

    println!("\nNetwork:");
    if report.network_cards.is_empty() {
        println!("  None detected");
    } else {
        for n in &report.network_cards {
            println!("  {} — {}", n.name, n.mac_address);
        }
    }

    // Drivers: /proc/modules has hundreds of entries — showing all would flood
    // the terminal. We show the count and the first 10 as a sample.
    println!("\nDrivers loaded: {}", report.drivers.len());
    for d in report.drivers.iter().take(10) {
        println!("  {} [{}]", d.name, d.status);
    }
    if report.drivers.len() > 10 {
        println!("  ... and {} more (see JSON for full list)", report.drivers.len() - 10);
    }

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    // ── JSON Output ───────────────────────────────────────────────────────────
    //
    // serde_json::to_string_pretty() converts the entire HardwareReport struct
    // to a nicely formatted JSON string. This works because every struct
    // has #[derive(Serialize)] at the top.
    //
    // This JSON is what Linux System Composer will read to:
    //   - Check GPU vendor for driver compatibility
    //   - Check CPU arch for kernel selection (x86-64-v3, etc.)
    //   - Check RAM for recommendations
    //   - Know which drivers are already loaded

    match serde_json::to_string_pretty(&report) {
        Ok(json) => {
            let path = "hardware_report.json";
            match fs::write(path, &json) {
                Ok(_)  => println!("\nJSON saved → {}", path),
                Err(e) => println!("\nFailed to save JSON: {}", e),
            }
        }
        Err(e) => println!("\nFailed to serialize: {}", e),
    }
}