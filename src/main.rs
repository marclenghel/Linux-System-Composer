use sysinfo::System;
use std::process::Command;

struct HardwareReport {
    os: String,
    kernel: String,
    cpu: String,
    total_ram_gb: f64,
    disks: Vec<String>,
}

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

fn main() {
    let report = detect();

    println!("OS:         {}", report.os);
    println!("Kernel:     {}", report.kernel);
    println!("CPU:        {}", report.cpu);

    let gpus = detect_gpus();
    if gpus.is_empty() {
        println!("No GPUs detected.");
        return;
    }
    println!("GPUs found: {}", gpus.len());

    for gpu in &gpus {
        println!("  Vendor:   {}", gpu.vendor);
        println!("  Model:    {}", gpu.name);
    }
    println!("RAM:        {:.2} GB", report.total_ram_gb);
    println!("Disks:");
    for disk in &report.disks {
        println!("   - {}", disk);
    }
}

fn detect_gpus() -> Vec<_GpuInfo> {
    let mut gpus = Vec::new();

    let output = Command::new("lspci")
        .output()
        .expect("Failed to run lspci");

    let text = String::from_utf8_lossy(&output.stdout);

    for line in text.lines() {
        let lower = line.to_lowercase();

        let is_gpu = lower.contains("vga compatible")
            || lower.contains("display controller")
            || lower.contains("3d controller");

        if is_gpu {
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
                "INTEL"
            } else {
                "Unknown"
            };

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

            gpus.push(_GpuInfo {
                vendor: vendor.to_string(),
                name: model,
            });
        }
    }

    gpus
}

struct _GpuInfo {
    vendor: String,
    name: String,
}