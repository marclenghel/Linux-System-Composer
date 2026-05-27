use sysinfo::System;

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

    println!("OS:     {}", report.os);
    println!("Kernel: {}", report.kernel);
    println!("CPU:    {}", report.cpu);
    println!("RAM:    {:.2} GB", report.total_ram_gb);
    println!("Disks:");
    for disk in &report.disks {
        println!("  - {}", disk);
    }
}