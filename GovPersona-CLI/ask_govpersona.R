# =============================================================================
# ask_govpersona.R  —  GovPersona CLI for R  (v2 — conversational + training)
#
# USAGE (from RStudio Console):
#   source("ask_govpersona.R")          # interactive mode
#
# USAGE (from command line / ask_r.bat):
#   Rscript ask_govpersona.R --org finance_ministry -q "Your question"
#   Rscript ask_govpersona.R --org central_bank -q "..." -o report.docx
#
# AGENTS:
#   1. finance_ministry           Ministry of Finance
#   2. central_bank               Bank of Israel
#   3. securities_authority       Israel Securities Authority
#   4. capital_markets_authority  Capital Markets, Insurance & Savings
#   5. ministry_of_justice        Ministry of Justice
#   6. tax_authority              Israel Tax Authority
#
# IN-SESSION COMMANDS (after each answer):
#   [Enter question]  Ask a follow-up (full conversation history is kept)
#   c                 Correct the last answer — saves correction to the KB
#   d                 Add a document (.txt or .docx) to this agent's KB
#   q                 Quit
# =============================================================================

suppressPackageStartupMessages({
  library(httr)
  library(jsonlite)
})

`%||%` <- function(a, b) if (!is.null(a)) a else b

get_script_dir <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg) > 0)
    return(normalizePath(dirname(sub("^--file=", "", file_arg[1]))))
  src <- tryCatch(
    normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)),
    error = function(e) NULL)
  if (!is.null(src) && nchar(src) > 0) return(src)
  getwd()
}

SCRIPT_DIR <- get_script_dir()


# =============================================================================
# 1.  Load .env
# =============================================================================
load_env <- function(dir) {
  env_file <- file.path(dir, ".env")
  if (!file.exists(env_file)) return(invisible(NULL))
  for (line in readLines(env_file, warn = FALSE, encoding = "UTF-8")) {
    line <- trimws(line)
    if (nchar(line) == 0 || startsWith(line, "#") || !grepl("=", line)) next
    parts <- strsplit(line, "=", fixed = TRUE)[[1]]
    key   <- trimws(parts[1])
    value <- trimws(paste(parts[-1], collapse = "="))
    do.call(Sys.setenv, setNames(list(value), key))
  }
}
load_env(SCRIPT_DIR)


# =============================================================================
# 2.  Parse arguments / interactive picker
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

  if (is.null(org)) {
    cat("\n  ╔══════════════════════════════════════╗\n")
    cat("  ║       GovPersona  (R edition)        ║\n")
    cat("  ╚══════════════════════════════════════╝\n\n")
    cat("  Available agents:\n")
    cat("    1. finance_ministry           Ministry of Finance\n")
    cat("    2. central_bank               Bank of Israel\n")
    cat("    3. securities_authority       Israel Securities Authority\n")
    cat("    4. capital_markets_authority  Capital Markets, Insurance & Savings\n")
    cat("    5. ministry_of_justice        Ministry of Justice\n")
    cat("    6. tax_authority              Israel Tax Authority\n\n")
    choice <- readline("  Choose agent (1-6 or name): ")
    org <- switch(trimws(choice),
      "1" = "finance_ministry",
      "2" = "central_bank",
      "3" = "securities_authority",
      "4" = "capital_markets_authority",
      "5" = "ministry_of_justice",
      "6" = "tax_authority",
      trimws(choice))
  }

  if (is.null(question)) {
    cat("\n")
    question <- readline("  First question: ")
  }

  if (is.null(out)) {
    ts  <- format(Sys.time(), "%Y-%m-%d_%H%M")
    out <- file.path(SCRIPT_DIR, paste0("answer_", org, "_", ts, ".docx"))
  }

  list(org = org, question = question, out = out, top_k = top_k)
}


# =============================================================================
# 3.  Knowledge base — load & search
# =============================================================================
load_kb <- function(kb_file) {
  cat("  Loading KB...", appendLF = FALSE)
  chunks <- jsonlite::fromJSON(kb_file, simplifyVector = FALSE)
  cat(sprintf(" %s chunks\n", format(length(chunks), big.mark = ",")))
  chunks
}

tokenize <- function(text) {
  tokens <- unlist(strsplit(
    tolower(gsub("[^\\w\\s]", " ", text, perl = TRUE)), "\\s+"))
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
# 4.  Prompts
# =============================================================================
build_context <- function(top_chunks) {
  if (length(top_chunks) == 0) return("[No documents found for this agency.]")
  parts <- mapply(function(chunk, i) {
    src <- chunk$source %||% "unknown"
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
  prompt <- gsub("{org_name}",    cfg$name,        prompt, fixed = TRUE)
  prompt <- gsub("{role_title}",  cfg$role_title,  prompt, fixed = TRUE)
  prompt <- gsub("{org_mandate}", cfg$org_mandate, prompt, fixed = TRUE)
  prompt <- gsub("{context}",     context,         prompt, fixed = TRUE)
  prompt
}


# =============================================================================
# 5.  Claude API  (accepts full messages list for multi-turn)
# =============================================================================
call_claude <- function(api_key, system_prompt, messages) {
  body <- list(
    model       = "claude-sonnet-4-6",
    max_tokens  = 2000L,
    temperature = 0.3,
    system      = system_prompt,
    messages    = messages
  )
  response <- httr::POST(
    url    = "https://api.anthropic.com/v1/messages",
    config = httr::config(ssl_verifypeer = FALSE),
    httr::add_headers(
      "x-api-key"         = api_key,
      "anthropic-version" = "2023-06-01",
      "content-type"      = "application/json"),
    body   = jsonlite::toJSON(body, auto_unbox = TRUE),
    encode = "raw")
  if (httr::http_error(response)) {
    stop("Claude API error (", httr::status_code(response), "): ",
         httr::content(response, "text", encoding = "UTF-8"))
  }
  parsed <- jsonlite::fromJSON(httr::content(response, "text", encoding = "UTF-8"))
  parsed$content$text[1]
}


# =============================================================================
# 6.  Persistent training — save correction / add document to KB JSON
# =============================================================================

# Save a user correction as a high-priority chunk at the top of the KB
save_correction <- function(kb_file, question, correction) {
  chunks <- jsonlite::fromJSON(kb_file, simplifyVector = FALSE)
  new_chunk <- list(
    text         = paste0(
      "USER CORRECTION\n",
      "Question: ", question, "\n",
      "Correct answer: ", correction),
    source       = paste0("correction_", format(Sys.Date(), "%Y-%m-%d")),
    chunk_index  = 0
  )
  # Prepend so keyword search finds it first
  combined <- c(list(new_chunk), chunks)
  jsonlite::write_json(combined, kb_file, auto_unbox = TRUE, pretty = FALSE)
  cat(sprintf(
    "\n  Correction saved. KB now has %s chunks.\n",
    format(length(combined), big.mark = ",")))
}

# Read a .txt or .docx file, chunk it, append to KB
add_document <- function(kb_file, org) {
  path <- trimws(readline(
    "  Path to file (.txt or .docx) — paste full path: "))

  if (!file.exists(path)) {
    cat("  File not found. Check the path and try again.\n")
    return(FALSE)
  }

  ext <- tolower(tools::file_ext(path))

  if (ext == "docx") {
    if (!requireNamespace("officer", quietly = TRUE)) {
      cat("  Need the 'officer' package to read .docx files.\n")
      cat("  Try saving the file as .txt instead.\n")
      return(FALSE)
    }
    library(officer)
    content <- docx_summary(read_docx(path))
    text <- paste(
      content$text[content$content_type == "paragraph" & !is.na(content$text)],
      collapse = "\n")
  } else if (ext == "txt") {
    text <- paste(
      readLines(path, warn = FALSE, encoding = "UTF-8"),
      collapse = "\n")
  } else {
    cat("  Only .txt and .docx files are supported.\n")
    return(FALSE)
  }

  words <- strsplit(trimws(text), "\\s+")[[1]]
  words <- words[nchar(words) > 0]
  if (length(words) == 0) {
    cat("  No text found in the file.\n")
    return(FALSE)
  }

  # Chunk into ~300-word blocks
  chunk_size <- 300
  fname      <- basename(path)
  new_chunks <- list()
  i <- 1; idx <- 1
  while (i <= length(words)) {
    end <- min(i + chunk_size - 1, length(words))
    new_chunks[[idx]] <- list(
      text        = paste(words[i:end], collapse = " "),
      source      = fname,
      chunk_index = idx)
    i <- end + 1; idx <- idx + 1
  }

  existing <- jsonlite::fromJSON(kb_file, simplifyVector = FALSE)
  combined <- c(new_chunks, existing)
  jsonlite::write_json(combined, kb_file, auto_unbox = TRUE, pretty = FALSE)
  cat(sprintf(
    "\n  Added %d chunks from '%s'. KB now has %s chunks.\n",
    length(new_chunks), fname, format(length(combined), big.mark = ",")))
  TRUE
}


# =============================================================================
# 7.  Word document output
# =============================================================================
save_docx <- function(messages, sources, cfg, out_path) {
  if (!requireNamespace("officer", quietly = TRUE))
    stop("The 'officer' package is not installed. Run install_r.R first.")
  library(officer)

  doc <- read_docx()

  title_prop  <- fp_text(font.size = 18, bold = TRUE,
                          color = "#1F497D", font.family = "Calibri")
  role_prop   <- fp_text(font.size = 11, italic = TRUE,
                          color = "#595959", font.family = "Calibri")
  date_prop   <- fp_text(font.size = 10, color = "#888888",
                          font.family = "Calibri")
  h2_prop     <- fp_text(font.size = 13, bold = TRUE,
                          color = "#1F497D", font.family = "Calibri")
  q_prop      <- fp_text(font.size = 11, italic = TRUE,
                          font.family = "Calibri")
  body_prop   <- fp_text(font.size = 11, font.family = "Calibri")
  source_prop <- fp_text(font.size = 10, color = "#444444",
                          font.family = "Calibri")
  footer_prop <- fp_text(font.size = 8, italic = TRUE,
                          color = "#AAAAAA", font.family = "Calibri")

  org_name_en <- if (!is.null(cfg$name_en)) cfg$name_en else cfg$name

  doc <- doc |>
    body_add_fpar(fpar(ftext(org_name_en, title_prop))) |>
    body_add_fpar(fpar(ftext(cfg$role_title, role_prop))) |>
    body_add_fpar(fpar(ftext(format(Sys.Date(), "%B %d, %Y"), date_prop))) |>
    body_add_par("", style = "Normal")

  # Write every Q/A exchange from the conversation
  for (i in seq_along(messages)) {
    msg <- messages[[i]]
    if (msg$role == "user") {
      doc <- doc |>
        body_add_fpar(fpar(ftext("Question", h2_prop))) |>
        body_add_fpar(fpar(ftext(msg$content, q_prop))) |>
        body_add_par("", style = "Normal")
    } else {
      doc <- doc |>
        body_add_fpar(fpar(ftext("Answer", h2_prop)))
      for (block in strsplit(msg$content, "\n\n")[[1]]) {
        block <- trimws(block)
        if (nchar(block) == 0) next
        lines     <- strsplit(block, "\n")[[1]]
        non_empty <- lines[nchar(trimws(lines)) > 0]
        is_bullet <- length(non_empty) > 1 &&
          all(grepl("^\\s*[-*\u2022]", non_empty))
        if (is_bullet) {
          for (line in non_empty) {
            lt <- trimws(sub("^\\s*[-*\u2022]\\s*", "", line))
            if (nchar(lt) > 0)
              doc <- body_add_fpar(doc,
                fpar(ftext(paste0("\u2022  ", lt), body_prop)))
          }
        } else {
          doc <- body_add_fpar(doc, fpar(ftext(block, body_prop)))
        }
      }
      doc <- body_add_par(doc, "", style = "Normal")
    }
  }

  # Sources
  unique_sources <- sort(unique(sources))
  if (length(unique_sources) > 0) {
    doc <- doc |>
      body_add_fpar(fpar(ftext("Sources Consulted", h2_prop)))
    for (src in unique_sources)
      doc <- body_add_fpar(doc,
        fpar(ftext(paste0("\u2022  ", src), source_prop)))
  }

  doc <- doc |>
    body_add_par("", style = "Normal") |>
    body_add_fpar(fpar(ftext(
      "Generated by GovPersona  |  Powered by Claude (Anthropic)",
      footer_prop)))

  print(doc, target = out_path)
  cat(sprintf("  Saved: %s\n", basename(out_path)))
}


# =============================================================================
# 8.  Main — conversation loop
# =============================================================================
main <- function() {
  args <- parse_args()

  # ── Validate setup ──────────────────────────────────────────────────────────
  api_key <- Sys.getenv("ANTHROPIC_API_KEY")
  if (nchar(api_key) == 0)
    stop("ANTHROPIC_API_KEY not set. Add it to .env next to this script.")

  agents_file <- file.path(SCRIPT_DIR, "agents_config.json")
  if (!file.exists(agents_file))
    stop("agents_config.json not found.")
  agents <- jsonlite::fromJSON(agents_file, simplifyVector = FALSE)
  if (is.null(agents[[args$org]]))
    stop(sprintf("Agent '%s' not found. Available: %s",
      args$org, paste(names(agents), collapse = ", ")))
  cfg <- agents[[args$org]]

  kb_file <- file.path(SCRIPT_DIR, paste0("kb_", args$org, ".json"))
  if (!file.exists(kb_file))
    stop(sprintf("KB not found: %s", kb_file))

  cat(sprintf("\n  Agent: %s\n\n", cfg$name))

  # ── Load KB ─────────────────────────────────────────────────────────────────
  chunks <- load_kb(kb_file)

  # ── Conversation state ───────────────────────────────────────────────────────
  messages     <- list()
  all_sources  <- character(0)
  turn         <- 0L
  current_q    <- args$question

  repeat {
    turn <- turn + 1L

    # Re-retrieve context for every new user question
    cat("  Searching KB...", appendLF = FALSE)
    top_chunks  <- keyword_search(chunks, current_q, top_k = args$top_k)
    new_sources <- vapply(top_chunks, function(c) c$source %||% "unknown",
                          character(1))
    all_sources <- union(all_sources, new_sources)
    context     <- build_context(top_chunks)
    cat(sprintf(" %d chunks\n", length(top_chunks)))

    # Rebuild system prompt with fresh context each turn
    system_prompt <- build_system_prompt(cfg, context)

    # Append user message
    messages <- c(messages, list(list(role = "user", content = current_q)))

    # Call Claude with full conversation history
    cat("  Asking Claude...", appendLF = FALSE)
    answer <- call_claude(api_key, system_prompt, messages)
    cat(" done\n\n")

    # Append assistant message
    messages <- c(messages, list(list(role = "assistant", content = answer)))

    # Print answer to console
    cat("  ─────────────────────────────────────────────────────\n")
    cat(gsub("\n", "\n  ", paste0("  ", answer)), "\n")
    cat("  ─────────────────────────────────────────────────────\n\n")

    # Save full conversation to docx (overwrites same file each turn)
    ts       <- format(Sys.time(), "%Y-%m-%d_%H%M")
    out_path <- sub("\\.docx$", paste0("_", ts, ".docx"), args$out)
    save_docx(messages, all_sources, cfg, out_path)

    # ── Prompt for next action ────────────────────────────────────────────────
    cat("\n  What next?\n")
    cat("    [type question]  Follow-up (conversation context is kept)\n")
    cat("    c                Correct this answer & save to KB\n")
    cat("    d                Add a document (.txt/.docx) to this agent's KB\n")
    cat("    q                Quit\n\n")
    choice <- trimws(readline("  > "))

    if (tolower(choice) == "q" || nchar(choice) == 0) {
      cat("\n  Session complete. Goodbye.\n\n")
      break
    }

    if (tolower(choice) == "c") {
      correction <- trimws(readline("  Type the correct answer: "))
      if (nchar(correction) > 0) {
        save_correction(kb_file, current_q, correction)
        # Reload KB so next search picks up the correction
        chunks <- load_kb(kb_file)
      }
      next_q <- trimws(readline("\n  Follow-up question (or Enter to quit): "))
      if (nchar(next_q) == 0) { cat("\n  Session complete.\n\n"); break }
      current_q <- next_q
      next
    }

    if (tolower(choice) == "d") {
      add_document(kb_file, args$org)
      chunks <- load_kb(kb_file)
      next_q <- trimws(readline("\n  Follow-up question (or Enter to quit): "))
      if (nchar(next_q) == 0) { cat("\n  Session complete.\n\n"); break }
      current_q <- next_q
      next
    }

    # Treat anything else as a follow-up question
    current_q <- choice
  }
}

main()
