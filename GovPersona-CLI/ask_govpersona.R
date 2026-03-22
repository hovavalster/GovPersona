# =============================================================================
# ask_govpersona.R  —  GovPersona CLI for R
#
# Asks an Israeli government agency a question and saves the answer as a
# Word document (.docx). Runs entirely on the work computer with no internet
# needed for installation.
#
# USAGE (from RStudio Console):
#   source("ask_govpersona.R")          # interactive mode — it will ask you
#
# USAGE (from command line / ask_r.bat):
#   Rscript ask_govpersona.R --org finance_ministry --question "..."
#   Rscript ask_govpersona.R --org central_bank -q "What is inflation?" -o report.docx
#
# AGENTS:
#   finance_ministry      Ministry of Finance (משרד האוצר)
#   central_bank          Bank of Israel (בנק ישראל)
#   securities_authority  Israel Securities Authority (רשות ניירות ערך)
# =============================================================================

suppressPackageStartupMessages({
  library(httr)
  library(jsonlite)
})

`%||%` <- function(a, b) if (!is.null(a)) a else b

get_script_dir <- function() {
  # When run via Rscript
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0) {
    return(normalizePath(dirname(sub("^--file=", "", file_arg[1]))))
  }
  # When sourced in RStudio
  src <- tryCatch(normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)), error = function(e) NULL)
  if (!is.null(src) && nchar(src) > 0) return(src)
  # Fallback
  getwd()
}

SCRIPT_DIR <- get_script_dir()


# =============================================================================
# 1.  Load .env file
# =============================================================================
load_env <- function(dir) {
  env_file <- file.path(dir, ".env")
  if (!file.exists(env_file)) return(invisible(NULL))
  lines <- readLines(env_file, warn = FALSE, encoding = "UTF-8")
  for (line in lines) {
    line <- trimws(line)
    if (nchar(line) == 0 || startsWith(line, "#") || !grepl("=", line)) next
    parts <- strsplit(line, "=", fixed = TRUE)[[1]]
    key   <- trimws(parts[1])
    value <- trimws(paste(parts[-1], collapse = "="))
    if (Sys.getenv(key) == "") Sys.setenv(tmp__ = value, .name = key)
    # setenv workaround for dynamic names:
    do.call(Sys.setenv, setNames(list(value), key))
  }
}

load_env(SCRIPT_DIR)


# =============================================================================
# 2.  Parse command-line arguments (or ask interactively)
# =============================================================================
parse_args <- function() {
  raw <- commandArgs(trailingOnly = TRUE)

  get_flag <- function(flags, default = NULL) {
    for (f in flags) {
      idx <- which(raw == f)
      if (length(idx) > 0 && idx[1] < length(raw)) return(raw[idx[1] + 1])
    }
    default
  }

  org      <- get_flag(c("--org"))
  question <- get_flag(c("--question", "-q"))
  out      <- get_flag(c("--out", "-o"))
  top_k    <- as.integer(get_flag(c("--top-k"), "7"))

  # Interactive mode if sourced from RStudio without args
  if (is.null(org)) {
    cat("\n  GovPersona CLI (R version)\n")
    cat("  ===========================\n\n")
    cat("  Available agents:\n")
    cat("    1. finance_ministry           Ministry of Finance\n")
    cat("    2. central_bank               Bank of Israel\n")
    cat("    3. securities_authority       Israel Securities Authority\n")
    cat("    4. capital_markets_authority  Capital Markets, Insurance & Savings\n")
    cat("    5. ministry_of_justice        Ministry of Justice\n")
    cat("    6. tax_authority              Israel Tax Authority\n\n")
    choice <- readline("  Enter agent name or number (1-6): ")
    org <- switch(trimws(choice),
      "1" = "finance_ministry",
      "2" = "central_bank",
      "3" = "securities_authority",
      "4" = "capital_markets_authority",
      "5" = "ministry_of_justice",
      "6" = "tax_authority",
      trimws(choice)
    )
  }

  if (is.null(question)) {
    cat("\n")
    question <- readline("  Enter your question: ")
  }

  if (is.null(out)) {
    date_str <- format(Sys.Date(), "%Y-%m-%d")
    out <- file.path(SCRIPT_DIR, paste0("answer_", org, "_", date_str, ".docx"))
  }

  list(org = org, question = question, out = out, top_k = top_k)
}


# =============================================================================
# 3.  Keyword search (no embeddings — pure R)
# =============================================================================
tokenize <- function(text) {
  tokens <- unlist(strsplit(tolower(gsub("[^\\w\\s]", " ", text, perl = TRUE)), "\\s+"))
  unique(tokens[nchar(tokens) >= 2])
}

keyword_search <- function(chunks, query, top_k = 7) {
  tokens <- tokenize(query)
  if (length(tokens) == 0) return(chunks[seq_len(min(top_k, length(chunks)))])

  scores <- vapply(chunks, function(chunk) {
    tl <- tolower(chunk$text)
    sum(vapply(tokens, function(t) grepl(t, tl, fixed = TRUE), logical(1)))
  }, numeric(1))

  idx <- order(scores, decreasing = TRUE)[seq_len(min(top_k, length(chunks)))]
  chunks[idx]
}


# =============================================================================
# 4.  Build context string and system prompt
# =============================================================================
build_context <- function(top_chunks) {
  if (length(top_chunks) == 0) return("[No documents found for this agency.]")
  parts <- mapply(function(chunk, i) {
    src <- if (!is.null(chunk$source)) chunk$source else "unknown"
    paste0("[Source ", i, ": ", src, "]\n", chunk$text)
  }, top_chunks, seq_along(top_chunks), SIMPLIFY = TRUE)
  paste(parts, collapse = "\n\n---\n\n")
}

SYSTEM_TEMPLATE <- "You are a senior official and institutional spokesperson for {org_name}, with deep expertise in its mandate, analytical frameworks, research tradition, and known policy positions.

YOUR TWO SOURCES OF KNOWLEDGE - use both, in order of preference:

1. UPLOADED DOCUMENTS (retrieved context below): When the answer is found here, cite the source and present it as the organization's documented position.

2. INSTITUTIONAL KNOWLEDGE: When uploaded documents do not cover the topic, draw on your broad knowledge of {org_name}'s known positions, economic principles it upholds, its past research and publications, and the analytical frameworks it applies. Senior officials are expected to articulate well-reasoned positions - not simply say 'no document covers this.'

HOW TO HANDLE EACH CASE:
- If the retrieved context directly answers the question: cite it and answer from it.
- If the retrieved context is partially relevant: use it as a starting point, then extend with institutional reasoning.
- If the retrieved context is not relevant: answer entirely from institutional knowledge. Open with 'Based on {org_name}'s known analytical framework...'
- NEVER refuse to engage with a substantive policy question.
- Do NOT fabricate specific statistics or named publications you cannot verify.

TONE AND LANGUAGE:
- Adopt the formal, professional register of a senior {role_title} from {org_name}.
- Respond in the SAME LANGUAGE as the user's question (Hebrew to Hebrew, English to English).
- Use {org_name}'s official terminology.

MANDATE: {org_mandate}

RETRIEVED CONTEXT FROM UPLOADED DOCUMENTS:
{context}"

build_system_prompt <- function(cfg, context) {
  prompt <- SYSTEM_TEMPLATE
  prompt <- gsub("{org_name}",   cfg$name,         prompt, fixed = TRUE)
  prompt <- gsub("{role_title}", cfg$role_title,   prompt, fixed = TRUE)
  prompt <- gsub("{org_mandate}",cfg$org_mandate,  prompt, fixed = TRUE)
  prompt <- gsub("{context}",    context,          prompt, fixed = TRUE)
  prompt
}


# =============================================================================
# 5.  Call Claude API via httr
#     (ssl_verifypeer = FALSE needed for corporate SSL inspection proxy)
# =============================================================================
call_claude <- function(api_key, system_prompt, question) {
  body <- list(
    model       = "claude-sonnet-4-6",
    max_tokens  = 2000L,
    temperature = 0.3,
    system      = system_prompt,
    messages    = list(list(role = "user", content = question))
  )

  response <- httr::POST(
    url    = "https://api.anthropic.com/v1/messages",
    config = httr::config(ssl_verifypeer = FALSE),   # needed for MoF proxy
    httr::add_headers(
      "x-api-key"         = api_key,
      "anthropic-version" = "2023-06-01",
      "content-type"      = "application/json"
    ),
    body   = jsonlite::toJSON(body, auto_unbox = TRUE),
    encode = "raw"
  )

  if (httr::http_error(response)) {
    content <- httr::content(response, "text", encoding = "UTF-8")
    stop("Claude API error (", httr::status_code(response), "): ", content)
  }

  parsed <- jsonlite::fromJSON(httr::content(response, "text", encoding = "UTF-8"))
  parsed$content$text[1]
}


# =============================================================================
# 6.  Save Word document via officer
# =============================================================================
save_docx <- function(question, answer, sources, cfg, out_path) {
  if (!requireNamespace("officer", quietly = TRUE)) {
    stop(
      "The 'officer' package is not installed.\n",
      "Run install_r.R to install it from the r_packages/ folder."
    )
  }
  library(officer)

  doc <- read_docx()

  # ── Title block ─────────────────────────────────────────────────────────────
  org_name_en <- if (!is.null(cfg$name_en)) cfg$name_en else cfg$name

  title_prop  <- fp_text(font.size = 18, bold = TRUE,
                          color = "#1F497D", font.family = "Calibri")
  role_prop   <- fp_text(font.size = 11, italic = TRUE,
                          color = "#595959", font.family = "Calibri")
  date_prop   <- fp_text(font.size = 10, color = "#888888", font.family = "Calibri")
  body_prop   <- fp_text(font.size = 11, font.family = "Calibri")
  source_prop <- fp_text(font.size = 10, color = "#444444", font.family = "Calibri")
  footer_prop <- fp_text(font.size = 8,  italic = TRUE,
                          color = "#AAAAAA", font.family = "Calibri")

  doc <- doc |>
    body_add_fpar(fpar(ftext(org_name_en, title_prop))) |>
    body_add_fpar(fpar(ftext(cfg$role_title, role_prop))) |>
    body_add_fpar(fpar(ftext(format(Sys.Date(), "%B %d, %Y"), date_prop))) |>
    body_add_par("", style = "Normal")

  # ── Question ─────────────────────────────────────────────────────────────────
  h2_prop <- fp_text(font.size = 13, bold = TRUE,
                      color = "#1F497D", font.family = "Calibri")
  q_prop  <- fp_text(font.size = 11, italic = TRUE, font.family = "Calibri")

  doc <- doc |>
    body_add_fpar(fpar(ftext("Question", h2_prop))) |>
    body_add_fpar(fpar(ftext(question, q_prop))) |>
    body_add_par("", style = "Normal")

  # ── Answer ───────────────────────────────────────────────────────────────────
  doc <- doc |>
    body_add_fpar(fpar(ftext("Answer", h2_prop)))

  blocks <- strsplit(answer, "\n\n")[[1]]
  for (block in blocks) {
    block <- trimws(block)
    if (nchar(block) == 0) next

    lines <- strsplit(block, "\n")[[1]]
    non_empty <- lines[nchar(trimws(lines)) > 0]
    is_bullet <- length(non_empty) > 1 &&
      all(grepl("^\\s*[-*\u2022]", non_empty))

    if (is_bullet) {
      for (line in non_empty) {
        line_text <- trimws(sub("^\\s*[-*\u2022]\\s*", "", line))
        if (nchar(line_text) > 0) {
          doc <- body_add_fpar(doc, fpar(ftext(paste0("\u2022  ", line_text), body_prop)))
        }
      }
    } else {
      doc <- body_add_fpar(doc, fpar(ftext(block, body_prop)))
    }
  }

  # ── Sources ──────────────────────────────────────────────────────────────────
  unique_sources <- sort(unique(sources))
  if (length(unique_sources) > 0) {
    doc <- doc |>
      body_add_par("", style = "Normal") |>
      body_add_fpar(fpar(ftext("Sources Consulted", h2_prop)))
    for (src in unique_sources) {
      doc <- body_add_fpar(doc, fpar(ftext(paste0("\u2022  ", src), source_prop)))
    }
  }

  # ── Footer ───────────────────────────────────────────────────────────────────
  doc <- doc |>
    body_add_par("", style = "Normal") |>
    body_add_fpar(fpar(ftext(
      "Generated by GovPersona  |  Powered by Claude (Anthropic)", footer_prop
    )))

  print(doc, target = out_path)
  cat(sprintf("\n  Saved: %s\n", out_path))
}


# =============================================================================
# 7.  Main
# =============================================================================
main <- function() {
  args <- parse_args()

  cat(sprintf("\n  GovPersona CLI (R)\n"))
  cat(sprintf("  Agent   : %s\n", args$org))
  cat(sprintf("  Question: %s\n",
    if (nchar(args$question) > 80)
      paste0(substr(args$question, 1, 80), "...") else args$question))
  cat(sprintf("  Output  : %s\n\n", args$out))

  # ── Load agent config ───────────────────────────────────────────────────────
  agents_file <- file.path(SCRIPT_DIR, "agents_config.json")
  if (!file.exists(agents_file)) {
    stop("agents_config.json not found. Run export_kb.py on your home laptop first.")
  }
  agents <- jsonlite::fromJSON(agents_file, simplifyVector = FALSE)

  if (is.null(agents[[args$org]])) {
    stop(sprintf(
      "Agent '%s' not found. Available: %s",
      args$org, paste(names(agents), collapse = ", ")
    ))
  }
  cfg <- agents[[args$org]]

  # ── Load knowledge base ─────────────────────────────────────────────────────
  kb_file <- file.path(SCRIPT_DIR, paste0("kb_", args$org, ".json"))
  if (!file.exists(kb_file)) {
    stop(sprintf(
      "Knowledge base not found: %s\nRun export_kb.py on your home laptop first.",
      kb_file
    ))
  }

  cat("  Loading knowledge base...", appendLF = FALSE)
  chunks <- jsonlite::fromJSON(kb_file, simplifyVector = FALSE)
  cat(sprintf(" %s chunks\n", format(length(chunks), big.mark = ",")))

  # ── Retrieve context ────────────────────────────────────────────────────────
  cat("  Searching for relevant context...", appendLF = FALSE)
  top_chunks <- keyword_search(chunks, args$question, top_k = args$top_k)
  sources    <- vapply(top_chunks, function(c) c$source %||% "unknown", character(1))
  cat(sprintf(" %d chunks selected\n", length(top_chunks)))
  for (i in seq_along(top_chunks)) {
    cat(sprintf("    - %s  (chunk %s)\n",
      top_chunks[[i]]$source %||% "?",
      top_chunks[[i]]$chunk_index %||% "?"))
  }

  # ── Build prompt ────────────────────────────────────────────────────────────
  context       <- build_context(top_chunks)
  system_prompt <- build_system_prompt(cfg, context)

  # ── Check API key ───────────────────────────────────────────────────────────
  api_key <- Sys.getenv("ANTHROPIC_API_KEY")
  if (nchar(api_key) == 0) {
    stop(
      "ANTHROPIC_API_KEY is not set.\n",
      "Add it to the .env file next to this script:\n",
      "  ANTHROPIC_API_KEY=sk-ant-..."
    )
  }

  # ── Call Claude ─────────────────────────────────────────────────────────────
  cat("\n  Calling Claude API...", appendLF = FALSE)
  answer <- call_claude(api_key, system_prompt, args$question)
  cat(" done\n")

  # ── Save Word document ──────────────────────────────────────────────────────
  save_docx(args$question, answer, sources, cfg, args$out)

  cat(sprintf(
    "\n  Open  %s  in Word to read the answer.\n\n",
    basename(args$out)
  ))
}

main()
