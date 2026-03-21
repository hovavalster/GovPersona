# install_shiny.R
# Run ONCE on your WORK COMPUTER to install packages from the r_packages/ folder.
#
# HOW TO RUN:
#   In RStudio: open this file and press Ctrl+Shift+Enter

script_dir <- tryCatch(
  normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)),
  error = function(e) {
    args <- commandArgs(trailingOnly = FALSE)
    f <- grep("^--file=", args, value = TRUE)
    if (length(f)) normalizePath(dirname(sub("^--file=", "", f[1]))) else getwd()
  }
)

pkg_dir <- file.path(script_dir, "r_packages")

if (!dir.exists(pkg_dir)) {
  stop(
    "r_packages/ folder not found.\n",
    "Run download_shiny_packages.R on your home laptop first, then copy this folder."
  )
}

zips <- list.files(pkg_dir, pattern = "\\.zip$", full.names = TRUE)

if (length(zips) == 0) {
  stop("No .zip files found in r_packages/. Run download_shiny_packages.R on your home laptop.")
}

cat(sprintf("\nInstalling %d package(s) from r_packages/...\n\n", length(zips)))

for (z in zips) {
  pkg_name <- sub("_.*", "", basename(z))
  if (pkg_name %in% rownames(installed.packages())) {
    cat(sprintf("  [already installed] %s\n", pkg_name))
    next
  }
  cat(sprintf("  Installing %-20s ...", pkg_name))
  tryCatch({
    install.packages(z, repos = NULL, type = "win.binary", quiet = TRUE)
    cat(" OK\n")
  }, error = function(e) {
    cat(sprintf(" FAILED: %s\n", conditionMessage(e)))
  })
}

cat("\n")
if ("shiny" %in% rownames(installed.packages())) {
  cat("  shiny is installed.\n")
  cat("  GovPersona Shiny is ready!\n\n")
  cat("  TO LAUNCH:\n")
  cat("    Option 1: Open app.R in RStudio -> click 'Run App' button\n")
  cat("    Option 2: Double-click start_shiny.bat\n")
  cat("    Option 3: In RStudio Console type: shiny::runApp('.')\n\n")
  cat("  Then open your browser at: http://127.0.0.1:4747\n\n")
} else {
  cat("  WARNING: shiny did not install. Check errors above.\n\n")
}
