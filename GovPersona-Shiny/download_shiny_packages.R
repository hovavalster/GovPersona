# download_shiny_packages.R
# Run ONCE on your HOME LAPTOP to download all required packages.
#
# HOW TO RUN:
#   In RStudio: open this file and press Ctrl+Shift+Enter
#   Or: Rscript download_shiny_packages.R

script_dir <- tryCatch(
  normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)),
  error = function(e) {
    args <- commandArgs(trailingOnly = FALSE)
    f <- grep("^--file=", args, value = TRUE)
    if (length(f)) normalizePath(dirname(sub("^--file=", "", f[1]))) else getwd()
  }
)

out_dir <- file.path(script_dir, "r_packages")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

cat(sprintf("\nDownloading R packages to: %s\n\n", out_dir))

# All packages needed (shiny + its deps + officer + zip)
pkgs <- c(
  "shiny", "httpuv", "htmltools", "later", "promises",
  "fastmap", "cachem", "memoise", "xtable", "sourcetools",
  "commonmark", "fontawesome", "bslib", "sass", "digest",
  "Rcpp", "otel",
  "officer", "zip"
)

# Only download what isn't already in out_dir
existing <- sub("_.*", "", list.files(out_dir, pattern = "\\.zip$"))
to_download <- pkgs[!pkgs %in% existing]

if (length(to_download) == 0) {
  cat("  All packages already downloaded.\n\n")
} else {
  downloaded <- download.packages(
    to_download,
    destdir = out_dir,
    type    = "win.binary",
    repos   = "https://cran.rstudio.com",
    quiet   = FALSE
  )
  cat(sprintf("\n  Downloaded %d package(s).\n", nrow(downloaded)))
}

cat("\n  Done! Now:\n")
cat("  1. Copy the entire GovPersona-Shiny/ folder to your work computer (USB)\n")
cat("  2. Open install_shiny.R in RStudio on the work computer and press Ctrl+Shift+Enter\n")
cat("  3. Open app.R and click Run App — or double-click start_shiny.bat\n\n")
