use sysinfo::System;
use std::process::Command;

// ── STRUCTS ───────────────────────────────────────────────────────────────────

struct HardwareReport {
    os: String,
    kernel: String,
    cpu: String,
    total_ram_gb: f64,
    disks: Vec<String>,
}

// Removed the underscore — _GpuInfo means "unused" in Rust convention
// Since we use it, it should just be GpuInfo
struct GpuInfo {
    vendor: String,
    name: String,
}

// ── OS CHECK ──────────────────────────────────────────────────────────────────

fn is_mac() -> bool {
    std::env::consts::OS == "macos"
}

// ── HARDWARE REPORT ───────────────────────────────────────────────────────────

fn detect() -> HardwareReport {
    let mut sys = System::new_all();
    sys.refresh_all();

    let cpu = sys.cpus()
        .first()
        .map(|c| c.brand().to_string())
        .unwrap_or("Unknown".to_string());

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

fn detect_mac_chip() -> String {
    // system_profiler gives us detailed hardware info on macOS
    // We look for "Chip:" (Apple Silicon) or "Processor Name:" (Intel Mac)
    let output = Command::new("system_profiler")
        .arg("SPHardwareDataType")
        .output();

    if let Ok(o) = output {
        let text = String::from_utf8_lossy(&o.stdout);

        for line in text.lines() {
            let lower = line.to_lowercase();

            // "Chip:" appears on Apple Silicon Macs (M1, M2, M3...)
            // "Processor Name:" appears on Intel Macs
            if lower.contains("chip:") || lower.contains("processor name:") {
                if let Some(colon_pos) = line.find(':') {
                    let chip_name = line[colon_pos + 1..].trim().to_string();
                    if !chip_name.is_empty() {
                        return chip_name;
                    }
                }
            }
        }
    }

    // Fallback: try sysctl directly (works reliably on Intel Macs)
    let fallback = Command::new("sysctl")
        .arg("-n")
        .arg("machdep.cpu.brand_string")
        .output();

    match fallback {
        Ok(o) => {
            let result = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if result.is_empty() {
                "Unknown Apple chip".to_string()
            } else {
                result
            }
        }
        Err(_) => "Unknown Apple chip".to_string(),
    }
}

// ── GPU DETECTION — MAC ───────────────────────────────────────────────────────

// On macOS, lspci doesn't exist. We use system_profiler SPDisplaysDataType instead.
// Its output looks like:
//
//   Graphics/Displays:
//       Apple M3 Pro:
//         Chipset Model: Apple M3 Pro
//         Type: GPU
//         Vendor: Apple (0x106b)
//
// We look for "Chipset Model:" lines to get the GPU name.

fn detect_gpus_mac() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    let output = Command::new("system_profiler")
        .arg("SPDisplaysDataType")
        .output();

    let output = match output {
        Ok(o) => o,
        Err(_) => {
            println!("system_profiler not found — cannot detect GPU on macOS.");
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

// ── GPU DETECTION — LINUX ─────────────────────────────────────────────────────

// On Linux we use lspci. Output looks like:
//
//   01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060] (rev a1)
//
// We filter for GPU lines, then extract vendor and model name.

fn detect_gpus_linux() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();

    let output = Command::new("lspci").output();

    let output = match output {
        Ok(o) => o,
        Err(_) => {
            println!("lspci not found. Install pciutils:");
            println!("  Arch:   sudo pacman -S pciutils");
            println!("  Debian: sudo apt install pciutils");
            println!("  Fedora: sudo dnf install pciutils");
            return gpus;
        }
    };

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        let lower = line.to_lowercase();

        let is_gpu = lower.contains("vga compatible")
            || lower.contains("display controller")
            || lower.contains("3d controller");

        if !is_gpu {
            continue;
        }

        let after_colon = line
            .splitn(3, ':')
            .nth(2)
            .unwrap_or(line)
            .trim();

        let lower_name = after_colon.to_lowercase();

        let vendor = if lower_name.contains("nvidia") {
            "NVIDIA"
        } else if lower_name.contains("amd") || lower_name.contains("advanced micro") {
            "AMD"
        } else if lower_name.contains("intel") {
            "Intel"
        } else {
            "Unknown"
        };

        // Search for ']' only AFTER '[' to avoid the begin > end panic
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

        gpus.push(GpuInfo {
            vendor: vendor.to_string(),
            name: model,
        });
    }

    gpus
}

// ── GPU ROUTER ────────────────────────────────────────────────────────────────

// Picks the right detection method based on OS.
// main() calls this and never needs to know which OS it's on.

fn detect_gpus() -> Vec<GpuInfo> {
    if is_mac() {
        detect_gpus_mac()
    } else {
        detect_gpus_linux()
    }
}

// ── MAIN ──────────────────────────────────────────────────────────────────────

fn main() {
    let report = detect();

    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
    println!("  Hardware Report");
    println!("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

    println!("OS:         {}", report.os);
    println!("Kernel:     {}", report.kernel);

    if is_mac() {
        println!("Chip:       {}", detect_mac_chip());
    }

    println!("CPU:        {}", report.cpu);
    println!("RAM:        {:.2} GB", report.total_ram_gb);

    println!("Disks:");
    for disk in &report.disks {
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