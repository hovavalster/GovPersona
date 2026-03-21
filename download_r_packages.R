# download_r_packages.R — Run on HOME laptop to download officer + zip for work computer
#
# HOW TO RUN:
#   In RStudio: open this file, click Source (Ctrl+Shift+Enter)
#   Or: Rscript download_r_packages.R

script_dir <- tryCatch(
  normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)),
  error = function(e) {
    args <- commandArgs(trailingOnly = FALSE)
    f <- grep("^--file=", args, value = TRUE)
    if (length(f)) normalizePath(dirname(sub("^--file=", "", f[1]))) else getwd()
  }
)

out_dir <- file.path(script_dir, "GovPersona-CLI", "r_packages")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

cat(sprintf("\nDownloading R packages to: %s\n\n", out_dir))

# officer and zip are the only packages not already on the work computer
pkgs <- c("officer", "zip")

downloaded <- download.packages(
  pkgs,
  destdir     = out_dir,
  type        = "win.binary",
  repos       = "https://cran.rstudio.com",
  quiet       = FALSE
)

cat(sprintf("\n  Downloaded %d package(s) to r_packages/\n", nrow(downloaded)))
cat("  Copy GovPersona-CLI/ to the work computer, then open install_r.R in RStudio.\n\n")
