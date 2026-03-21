# install_r.R — Run ONCE on work computer to install officer from local files
#
# HOW TO RUN:
#   In RStudio: open this file, click Source (or press Ctrl+Shift+Enter)
#   Or from command line: Rscript install_r.R

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
    "r_packages/ folder not found at: ", pkg_dir, "\n",
    "Download packages on your home laptop first using download_r_packages.R"
  )
}

zips <- list.files(pkg_dir, pattern = "\\.zip$", full.names = TRUE)

if (length(zips) == 0) {
  stop("No .zip files found in r_packages/. Run download_r_packages.R on your home laptop.")
}

cat(sprintf("\nInstalling %d package(s) from r_packages/ folder...\n\n", length(zips)))

for (z in zips) {
  pkg_name <- sub("_.*", "", basename(z))
  if (pkg_name %in% rownames(installed.packages())) {
    cat(sprintf("  [already installed] %s\n", basename(z)))
    next
  }
  cat(sprintf("  Installing %s ...", basename(z)))
  tryCatch({
    install.packages(z, repos = NULL, type = "win.binary", quiet = TRUE)
    cat(" OK\n")
  }, error = function(e) {
    cat(sprintf(" FAILED: %s\n", conditionMessage(e)))
  })
}

cat("\n")
if ("officer" %in% rownames(installed.packages())) {
  cat("  officer is installed. GovPersona R is ready!\n")
  cat("  To ask a question:\n")
  cat("    - Double-click ask_r.bat, or\n")
  cat("    - Open ask_govpersona.R in RStudio and press Ctrl+Shift+Enter\n\n")
} else {
  cat("  WARNING: officer did not install. Check the error messages above.\n\n")
}
