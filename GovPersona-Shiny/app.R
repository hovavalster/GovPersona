# =============================================================================
# GovPersona Shiny Web App
# Tabs: Chat | Council | Agents | Training
# =============================================================================

suppressPackageStartupMessages({
  library(shiny)
  library(httr)
  library(jsonlite)
})

`%||%` <- function(a, b) if (!is.null(a)) a else b

# =============================================================================
# App directory
# =============================================================================
get_app_dir <- function() {
  d <- tryCatch(normalizePath(dirname(rstudioapi::getSourceEditorContext()$path)),
                error = function(e) NULL)
  if (!is.null(d) && nchar(d) > 0 && d != ".") return(d)
  getwd()
}
APP_DIR <- get_app_dir()

# =============================================================================
# Load .env
# =============================================================================
load_env <- function(dir) {
  env_file <- file.path(dir, ".env")
  if (!file.exists(env_file)) return(invisible(NULL))
  lines <- readLines(env_file, warn = FALSE, encoding = "UTF-8")
  for (line in lines) {
    line <- trimws(line)
    if (nchar(line) == 0 || startsWith(line, "#") || !grepl("=", line)) next
    parts <- strsplit(line, "=", fixed = TRUE)[[1]]
    do.call(Sys.setenv, setNames(list(trimws(paste(parts[-1], collapse = "="))), trimws(parts[1])))
  }
}
load_env(APP_DIR)

# =============================================================================
# Load agents + knowledge bases
# =============================================================================
agents_file <- file.path(APP_DIR, "agents_config.json")
if (!file.exists(agents_file)) stop("agents_config.json not found.")
AGENTS <- jsonlite::fromJSON(agents_file, simplifyVector = FALSE)

load_kb <- function(org) {
  kb_file <- file.path(APP_DIR, paste0("kb_", org, ".json"))
  if (!file.exists(kb_file)) return(list())
  jsonlite::fromJSON(kb_file, simplifyVector = FALSE)
}

KB_CACHE <- list()
for (org in names(AGENTS)) KB_CACHE[[org]] <- load_kb(org)

agent_choices <- setNames(names(AGENTS),
                          sapply(names(AGENTS), function(k) AGENTS[[k]]$name_en))

# =============================================================================
# Keyword search  (KB chunks and corrections)
# =============================================================================
tokenize <- function(text) {
  tokens <- unlist(strsplit(tolower(gsub("[^\\w\\s]", " ", text, perl = TRUE)), "\\s+"))
  unique(tokens[nchar(tokens) >= 2])
}

keyword_search <- function(chunks, query, top_k = 7) {
  if (length(chunks) == 0) return(list())
  tokens <- tokenize(query)
  if (length(tokens) == 0) return(chunks[seq_len(min(top_k, length(chunks)))])
  scores <- vapply(chunks, function(chunk) {
    tl <- tolower(chunk$text)
    sum(vapply(tokens, function(t) grepl(t, tl, fixed = TRUE), logical(1)))
  }, numeric(1))
  chunks[order(scores, decreasing = TRUE)[seq_len(min(top_k, length(chunks)))]]
}

# =============================================================================
# Corrections  (per-agent training memory)
# =============================================================================
corrections_dir <- function() {
  d <- file.path(APP_DIR, "corrections")
  dir.create(d, showWarnings = FALSE)
  d
}

corrections_file <- function(org) {
  file.path(corrections_dir(), paste0("corrections_", org, ".json"))
}

load_corrections <- function(org) {
  f <- corrections_file(org)
  if (!file.exists(f)) return(list())
  tryCatch(jsonlite::fromJSON(f, simplifyVector = FALSE), error = function(e) list())
}

save_correction <- function(org, question, original_answer, correction) {
  existing <- load_corrections(org)
  new_entry <- list(
    question        = question,
    original_answer = original_answer,
    correction      = correction,
    timestamp       = format(Sys.time(), "%Y-%m-%d %H:%M:%S")
  )
  updated <- c(existing, list(new_entry))
  jsonlite::write_json(updated, corrections_file(org), pretty = TRUE, auto_unbox = TRUE)
}

delete_correction <- function(org, idx) {
  existing <- load_corrections(org)
  if (idx < 1 || idx > length(existing)) return(invisible(NULL))
  updated <- existing[-idx]
  jsonlite::write_json(updated, corrections_file(org), pretty = TRUE, auto_unbox = TRUE)
}

# Find corrections relevant to the current question (keyword match on question text)
find_relevant_corrections <- function(corrections, query, top_k = 3) {
  if (length(corrections) == 0) return(list())
  tokens <- tokenize(query)
  if (length(tokens) == 0) return(corrections[seq_len(min(top_k, length(corrections)))])
  scores <- vapply(corrections, function(c) {
    tl <- tolower(c$question)
    sum(vapply(tokens, function(t) grepl(t, tl, fixed = TRUE), logical(1)))
  }, numeric(1))
  top <- corrections[order(scores, decreasing = TRUE)[seq_len(min(top_k, length(corrections)))]]
  # Only return corrections with at least 1 matching token
  top[vapply(top, function(c) {
    tl <- tolower(c$question)
    any(vapply(tokens, function(t) grepl(t, tl, fixed = TRUE), logical(1)))
  }, logical(1))]
}

# =============================================================================
# System prompt
# =============================================================================
SYSTEM_TEMPLATE <- "You are a senior official and institutional spokesperson for {org_name}, with deep expertise in its mandate, analytical frameworks, research tradition, and known policy positions.

YOUR TWO SOURCES OF KNOWLEDGE:

1. UPLOADED DOCUMENTS (retrieved context below): When the answer is found here, cite the source and present it as the organization's documented position.

2. INSTITUTIONAL KNOWLEDGE: When uploaded documents do not cover the topic, draw on your broad knowledge of {org_name}'s known positions, economic principles it upholds, its past research and publications, and the analytical frameworks it applies.

HOW TO HANDLE EACH CASE:
- If the retrieved context directly answers the question: cite it and answer from it.
- If the retrieved context is partially relevant: use it as a starting point, then extend with institutional reasoning.
- If the retrieved context is not relevant: answer entirely from institutional knowledge.
- NEVER refuse to engage with a substantive policy question.
- Do NOT fabricate specific statistics or named publications you cannot verify.

TONE AND LANGUAGE:
- Adopt the formal, professional register of a senior {role_title} from {org_name}.
- Respond in the SAME LANGUAGE as the user's question (Hebrew to Hebrew, English to English).

MANDATE: {org_mandate}

{corrections_block}
RETRIEVED CONTEXT FROM UPLOADED DOCUMENTS:
{context}"

build_system_prompt <- function(cfg, context, corrections = list()) {
  corr_block <- ""
  if (length(corrections) > 0) {
    lines <- sapply(corrections, function(c) {
      paste0("Q: ", c$question, "\nCorrect answer: ", c$correction)
    })
    corr_block <- paste0(
      "IMPORTANT — SUPERVISOR CORRECTIONS (apply these when answering similar questions):\n",
      paste(lines, collapse = "\n\n"),
      "\n\n"
    )
  }
  prompt <- SYSTEM_TEMPLATE
  prompt <- gsub("{org_name}",         cfg$name,        prompt, fixed = TRUE)
  prompt <- gsub("{role_title}",       cfg$role_title,  prompt, fixed = TRUE)
  prompt <- gsub("{org_mandate}",      cfg$org_mandate, prompt, fixed = TRUE)
  prompt <- gsub("{corrections_block}", corr_block,     prompt, fixed = TRUE)
  prompt <- gsub("{context}",          context,         prompt, fixed = TRUE)
  prompt
}

build_context <- function(top_chunks) {
  if (length(top_chunks) == 0) return("[No documents found for this agency.]")
  parts <- mapply(function(chunk, i) {
    src <- if (!is.null(chunk$source)) chunk$source else "unknown"
    paste0("[Source ", i, ": ", src, "]\n", chunk$text)
  }, top_chunks, seq_along(top_chunks), SIMPLIFY = TRUE)
  paste(parts, collapse = "\n\n---\n\n")
}

# =============================================================================
# Claude API
# =============================================================================
call_claude <- function(api_key, system_prompt, messages, max_tokens = 2000) {
  body <- list(
    model       = "claude-sonnet-4-6",
    max_tokens  = as.integer(max_tokens),
    temperature = 0.3,
    system      = system_prompt,
    messages    = messages
  )
  response <- httr::POST(
    url    = "https://api.anthropic.com/v1/messages",
    config = httr::config(ssl_verifypeer = FALSE),
    httr::add_headers("x-api-key" = api_key, "anthropic-version" = "2023-06-01",
                      "content-type" = "application/json"),
    body   = jsonlite::toJSON(body, auto_unbox = TRUE),
    encode = "raw"
  )
  if (httr::http_error(response))
    stop("Claude API error (", httr::status_code(response), "): ",
         httr::content(response, "text", encoding = "UTF-8"))
  parsed <- jsonlite::fromJSON(httr::content(response, "text", encoding = "UTF-8"),
                               simplifyVector = FALSE)
  parsed$content[[1]]$text
}

# =============================================================================
# Word export
# =============================================================================
save_docx <- function(question, answer, sources, cfg, out_path) {
  library(officer)
  doc        <- read_docx()
  title_prop <- fp_text(font.size = 18, bold = TRUE,   color = "#1F497D", font.family = "Calibri")
  role_prop  <- fp_text(font.size = 11, italic = TRUE, color = "#595959", font.family = "Calibri")
  date_prop  <- fp_text(font.size = 10, color = "#888888", font.family = "Calibri")
  h2_prop    <- fp_text(font.size = 13, bold = TRUE,   color = "#1F497D", font.family = "Calibri")
  q_prop     <- fp_text(font.size = 11, italic = TRUE, font.family = "Calibri")
  body_prop  <- fp_text(font.size = 11, font.family = "Calibri")
  src_prop   <- fp_text(font.size = 10, color = "#444444", font.family = "Calibri")
  foot_prop  <- fp_text(font.size = 8,  italic = TRUE, color = "#AAAAAA", font.family = "Calibri")

  doc <- doc |>
    body_add_fpar(fpar(ftext(cfg$name_en %||% cfg$name, title_prop))) |>
    body_add_fpar(fpar(ftext(cfg$role_title, role_prop))) |>
    body_add_fpar(fpar(ftext(format(Sys.Date(), "%B %d, %Y"), date_prop))) |>
    body_add_par("", style = "Normal") |>
    body_add_fpar(fpar(ftext("Question", h2_prop))) |>
    body_add_fpar(fpar(ftext(question, q_prop))) |>
    body_add_par("", style = "Normal") |>
    body_add_fpar(fpar(ftext("Answer", h2_prop)))

  for (block in strsplit(answer, "\n\n")[[1]]) {
    block <- trimws(block)
    if (nchar(block) == 0) next
    lines <- strsplit(block, "\n")[[1]]
    ne    <- lines[nchar(trimws(lines)) > 0]
    if (length(ne) > 1 && all(grepl("^\\s*[-*\u2022]", ne))) {
      for (line in ne) {
        lt <- trimws(sub("^\\s*[-*\u2022]\\s*", "", line))
        if (nchar(lt) > 0) doc <- body_add_fpar(doc, fpar(ftext(paste0("\u2022  ", lt), body_prop)))
      }
    } else {
      doc <- body_add_fpar(doc, fpar(ftext(block, body_prop)))
    }
  }

  if (length(unique(sources)) > 0) {
    doc <- doc |> body_add_par("", style = "Normal") |>
      body_add_fpar(fpar(ftext("Sources Consulted", h2_prop)))
    for (src in sort(unique(sources)))
      doc <- body_add_fpar(doc, fpar(ftext(paste0("\u2022  ", src), src_prop)))
  }
  doc <- doc |> body_add_par("", style = "Normal") |>
    body_add_fpar(fpar(ftext("Generated by GovPersona  |  Powered by Claude (Anthropic)", foot_prop)))
  print(doc, target = out_path)
  out_path
}

# =============================================================================
# CSS
# =============================================================================
app_css <- "
body { font-family: 'Segoe UI', Arial, sans-serif; background: #f5f6fa; }
.navbar { background-color: #1F497D !important; }
.navbar-brand, .navbar-nav > li > a { color: #ffffff !important; }
.navbar-nav > li.active > a { background-color: #163a6b !important; }

.agent-badge {
  display: inline-block; padding: 4px 12px; border-radius: 20px;
  background: #e8f0fe; color: #1F497D; font-weight: 600; font-size: 13px;
  margin-bottom: 12px;
}
.chat-container {
  height: 460px; overflow-y: auto; padding: 16px;
  background: #ffffff; border: 1px solid #dde3f0; border-radius: 8px;
  margin-bottom: 12px;
}
.msg-user {
  background: #1F497D; color: #fff; border-radius: 12px 12px 2px 12px;
  padding: 10px 14px; margin: 6px 0 6px 60px; word-wrap: break-word;
}
.msg-agent {
  background: #f0f4ff; color: #222; border-radius: 12px 12px 12px 2px;
  padding: 10px 14px; margin: 6px 60px 6px 0; word-wrap: break-word;
  white-space: pre-wrap;
}
.msg-label { font-size: 11px; color: #888; margin-top: 2px; }
.msg-sources { font-size: 11px; color: #666; margin-top: 4px; font-style: italic; }

.feedback-bar {
  margin: 2px 60px 10px 0; display: flex; gap: 8px; align-items: center;
}
.btn-feedback-ok {
  background: #e6f4ea; color: #2d7a3a; border: 1px solid #b7dfbc;
  border-radius: 16px; padding: 3px 12px; font-size: 12px; cursor: pointer;
}
.btn-feedback-ok:hover { background: #c8eacf; }
.btn-feedback-fix {
  background: #fff3e0; color: #c0520a; border: 1px solid #f5c987;
  border-radius: 16px; padding: 3px 12px; font-size: 12px; cursor: pointer;
}
.btn-feedback-fix:hover { background: #ffe0b2; }
.correction-saved {
  font-size: 12px; color: #2d7a3a; font-style: italic; padding: 3px 0;
}

.council-card {
  background: #fff; border: 1px solid #dde3f0; border-radius: 8px;
  padding: 16px; margin-bottom: 14px;
}
.council-card h4 { color: #1F497D; margin-top: 0; }
.synthesis-card {
  background: #f0f4ff; border: 2px solid #1F497D; border-radius: 8px;
  padding: 16px; margin-top: 8px;
}
.synthesis-card h4 { color: #1F497D; margin-top: 0; }
.status-bar {
  background: #e8f0fe; color: #1F497D; padding: 8px 12px;
  border-radius: 6px; margin-bottom: 10px; font-size: 13px;
}
.correction-card {
  background: #fffdf0; border: 1px solid #f5c987; border-radius: 8px;
  padding: 14px; margin-bottom: 10px;
}
.correction-q  { font-weight: 600; color: #333; margin-bottom: 4px; }
.correction-a  { color: #555; white-space: pre-wrap; }
.correction-ts { font-size: 11px; color: #999; margin-top: 6px; }
"

# =============================================================================
# UI
# =============================================================================
ui <- navbarPage(
  title  = "GovPersona",
  id     = "nav",
  header = tags$head(tags$style(HTML(app_css))),

  # ── Chat ────────────────────────────────────────────────────────────────────
  tabPanel("Chat",
    fluidPage(fluidRow(
      column(3,
        wellPanel(
          tags$h4("Agent", style = "color:#1F497D; margin-top:0;"),
          selectInput("chat_agent", NULL, choices = agent_choices, width = "100%"),
          hr(),
          tags$h4("Options", style = "color:#1F497D;"),
          sliderInput("chat_top_k", "Context chunks:", min = 3, max = 15, value = 7),
          hr(),
          actionButton("chat_clear", "Clear Chat", icon = icon("trash"),
                       class = "btn-default btn-sm", style = "width:100%;"),
          br(), br(),
          downloadButton("chat_export", "Export to Word",
                         style = "width:100%; background:#1F497D; color:#fff; border:none;")
        )
      ),
      column(9,
        uiOutput("chat_agent_badge"),
        div(id = "chat_box", class = "chat-container", uiOutput("chat_history")),
        fluidRow(
          column(10,
            textAreaInput("chat_question", NULL, placeholder = "Ask a question...",
                          rows = 2, width = "100%")
          ),
          column(2,
            br(),
            actionButton("chat_send", "Send", icon = icon("paper-plane"),
                         style = "width:100%; background:#1F497D; color:#fff; border:none; height:58px;")
          )
        ),
        uiOutput("chat_status")
      )
    ))
  ),

  # ── Council ─────────────────────────────────────────────────────────────────
  tabPanel("Council",
    fluidPage(fluidRow(
      column(4,
        wellPanel(
          tags$h4("Multi-Agent Council", style = "color:#1F497D; margin-top:0;"),
          tags$p("Agents respond from their institutional perspectives, then a Rapporteur synthesizes.",
                 style = "color:#555; font-size:13px;"),
          hr(),
          tags$h5("Participating Agents"),
          checkboxGroupInput("council_agents", NULL,
            choices = agent_choices, selected = names(agent_choices)),
          hr(),
          textAreaInput("council_topic", "Topic / Question:", rows = 3,
                        placeholder = "e.g. What is the outlook for Israeli inflation in 2025?",
                        width = "100%"),
          actionButton("council_run", "Run Council", icon = icon("users"),
                       style = "width:100%; background:#1F497D; color:#fff; border:none; margin-top:8px;"),
          br(), br(),
          downloadButton("council_export", "Export to Word",
                         style = "width:100%; background:#1F497D; color:#fff; border:none;")
        )
      ),
      column(8,
        uiOutput("council_status"),
        uiOutput("council_output")
      )
    ))
  ),

  # ── Training ────────────────────────────────────────────────────────────────
  tabPanel("Training",
    fluidPage(
      fluidRow(
        column(4,
          wellPanel(
            tags$h4("Agent Training Memory", style = "color:#1F497D; margin-top:0;"),
            tags$p("Corrections you submit in the Chat tab are saved here.",
                   style = "color:#555; font-size:13px;"),
            tags$p("They are automatically applied to future questions to the same agent.",
                   style = "color:#555; font-size:13px;"),
            hr(),
            selectInput("train_agent", "View corrections for:", choices = agent_choices, width = "100%"),
            actionButton("train_refresh", "Refresh", icon = icon("refresh"),
                         class = "btn-default btn-sm", style = "width:100%;")
          )
        ),
        column(8,
          uiOutput("train_summary"),
          uiOutput("train_corrections_list")
        )
      )
    )
  ),

  # ── Agents ──────────────────────────────────────────────────────────────────
  tabPanel("Agents",
    fluidPage(
      tags$h3("Available Agents", style = "color:#1F497D;"),
      uiOutput("agents_cards")
    )
  )
)

# =============================================================================
# Server
# =============================================================================
server <- function(input, output, session) {

  api_key <- reactive({
    k <- Sys.getenv("ANTHROPIC_API_KEY")
    if (nchar(k) == 0) stop("ANTHROPIC_API_KEY not set. Add it to the .env file.")
    k
  })

  # ── Chat state ───────────────────────────────────────────────────────────────
  chat_history   <- reactiveVal(list())
  chat_is_busy   <- reactiveVal(FALSE)
  last_chat_data <- reactiveVal(NULL)    # for Word export
  last_msg_id    <- reactiveVal(NULL)    # tracks the last assistant message for feedback

  output$chat_agent_badge <- renderUI({
    cfg <- AGENTS[[input$chat_agent]]
    corr_count <- length(load_corrections(input$chat_agent))
    badge_extra <- if (corr_count > 0)
      tags$span(style = "margin-left:8px; font-size:11px; color:#c0520a;",
                icon("graduation-cap"), " ", corr_count, " correction(s) active")
    else NULL
    tagList(
      tags$div(class = "agent-badge", icon("building"), " ", cfg$name_en %||% cfg$name),
      badge_extra
    )
  })

  output$chat_history <- renderUI({
    msgs   <- chat_history()
    n      <- length(msgs)
    if (n == 0)
      return(tags$p("Start a conversation by typing a question below.",
                    style = "color:#aaa; text-align:center; margin-top:40px;"))

    lapply(seq_along(msgs), function(i) {
      m <- msgs[[i]]
      if (m$role == "user") {
        tags$div(
          tags$div(class = "msg-user", m$content),
          tags$div(class = "msg-label", style = "text-align:right;", "You")
        )
      } else {
        # Sources line
        srcs_ui <- if (length(m$sources) > 0)
          tags$div(class = "msg-sources",
                   paste("Sources:", paste(unique(m$sources), collapse = " | ")))
        else NULL

        # Feedback bar — only on the last assistant message and when not busy
        is_last_assistant <- (i == n && !chat_is_busy())
        feedback_ui <- if (is_last_assistant) {
          tags$div(class = "feedback-bar",
            tags$span(style = "font-size:11px; color:#999;", "Was this answer correct?"),
            tags$button(
              class = "btn-feedback-ok",
              onclick = "Shiny.setInputValue('feedback_ok', Math.random())",
              "\u2705 Yes, looks right"
            ),
            tags$button(
              class = "btn-feedback-fix",
              onclick = "Shiny.setInputValue('feedback_fix', Math.random())",
              "\u270f Correct it"
            )
          )
        } else NULL

        tags$div(
          tags$div(class = "msg-agent", m$content),
          srcs_ui,
          tags$div(class = "msg-label", m$agent),
          feedback_ui
        )
      }
    })
  })

  output$chat_status <- renderUI({
    if (chat_is_busy())
      tags$div(class = "status-bar", icon("spinner", class = "fa-spin"), " Calling Claude API...")
  })

  # Scroll chat to bottom
  observe({
    chat_history()
    session$sendCustomMessage("scrollChat", list())
  })

  # Send message
  observeEvent(input$chat_send, {
    req(!chat_is_busy())
    question <- trimws(input$chat_question)
    if (nchar(question) == 0) return()
    updateTextAreaInput(session, "chat_question", value = "")

    hist <- c(chat_history(), list(list(role = "user", content = question)))
    chat_history(hist)
    chat_is_busy(TRUE)

    # Build Claude messages (last 20 turns max)
    turns      <- if (length(hist) > 20) tail(hist, 20) else hist
    claude_msgs <- lapply(turns, function(m) list(role = m$role, content = m$content))

    org        <- input$chat_agent
    cfg        <- AGENTS[[org]]
    chunks     <- KB_CACHE[[org]]
    top_chunks <- keyword_search(chunks, question, top_k = input$chat_top_k)
    sources    <- vapply(top_chunks, function(c) c$source %||% "unknown", character(1))
    context    <- build_context(top_chunks)

    # Load and apply relevant corrections
    all_corr     <- load_corrections(org)
    rel_corr     <- find_relevant_corrections(all_corr, question, top_k = 3)
    sys_prompt   <- build_system_prompt(cfg, context, corrections = rel_corr)

    answer <- tryCatch(call_claude(api_key(), sys_prompt, claude_msgs),
                       error = function(e) paste("Error:", conditionMessage(e)))

    msg_id <- as.character(as.numeric(Sys.time()))
    hist <- c(chat_history(), list(list(
      role    = "assistant",
      content = answer,
      sources = sources,
      agent   = cfg$name_en %||% cfg$name,
      org     = org,
      msg_id  = msg_id
    )))
    chat_history(hist)
    chat_is_busy(FALSE)
    last_msg_id(msg_id)
    last_chat_data(list(question = question, answer = answer, sources = sources, cfg = cfg))
  })

  # Feedback: looks correct — just acknowledge
  observeEvent(input$feedback_ok, {
    showNotification("Got it — answer marked as correct.", type = "message", duration = 3)
  })

  # Feedback: open correction modal
  observeEvent(input$feedback_fix, {
    hist <- chat_history()
    last_asst <- NULL
    last_user <- NULL
    for (m in rev(hist)) {
      if (is.null(last_asst) && m$role == "assistant") last_asst <- m
      if (!is.null(last_asst) && m$role == "user") { last_user <- m; break }
    }
    if (is.null(last_asst)) return()

    showModal(modalDialog(
      title = tags$span(icon("graduation-cap"), " Correct this answer"),
      size  = "l",
      tags$p(tags$b("Your question:"),
             tags$span(style = "color:#555;", last_user$content %||% "(unknown)")),
      tags$p(tags$b("Original answer:"),
             style = "margin-bottom:4px;"),
      tags$div(
        style = "background:#f0f4ff; border-radius:6px; padding:10px; font-size:13px;
                 white-space:pre-wrap; max-height:150px; overflow-y:auto; margin-bottom:12px;",
        last_asst$content
      ),
      tags$p(tags$b("Your correction:"),
             tags$span(style = "color:#888; font-size:12px;",
                       " — write the correct answer below. The agent will remember this.")),
      textAreaInput("modal_correction", NULL,
                    value = "", rows = 6, width = "100%",
                    placeholder = "Type the correct / improved answer here..."),
      footer = tagList(
        modalButton("Cancel"),
        actionButton("modal_save_correction", "Save Correction",
                     icon = icon("save"),
                     style = "background:#1F497D; color:#fff; border:none;")
      ),
      # Store context for the save handler
      tags$input(type = "hidden", id = "modal_org",
                 value = last_asst$org %||% input$chat_agent),
      tags$input(type = "hidden", id = "modal_question",
                 value = last_user$content %||% ""),
      tags$input(type = "hidden", id = "modal_orig_answer",
                 value = last_asst$content)
    ))
  })

  # Save correction from modal
  observeEvent(input$modal_save_correction, {
    correction <- trimws(input$modal_correction)
    if (nchar(correction) == 0) {
      showNotification("Please write a correction before saving.", type = "warning")
      return()
    }

    # Read hidden fields via JS eval
    hist     <- chat_history()
    last_asst <- NULL; last_user <- NULL
    for (m in rev(hist)) {
      if (is.null(last_asst) && m$role == "assistant") last_asst <- m
      if (!is.null(last_asst) && m$role == "user") { last_user <- m; break }
    }
    org      <- last_asst$org %||% input$chat_agent
    question <- last_user$content %||% ""
    orig_ans <- last_asst$content %||% ""

    save_correction(org, question, orig_ans, correction)
    removeModal()
    showNotification(
      paste0("Correction saved for ", AGENTS[[org]]$name_en, ". It will be applied in future answers."),
      type = "message", duration = 5
    )
    # Refresh badge
    session$sendCustomMessage("refreshBadge", list())
  })

  # Clear chat
  observeEvent(input$chat_clear, {
    chat_history(list())
    last_chat_data(NULL)
  })

  # Word export
  output$chat_export <- downloadHandler(
    filename = function() paste0("govpersona_chat_", format(Sys.Date(), "%Y-%m-%d"), ".docx"),
    content  = function(file) {
      d <- last_chat_data()
      if (is.null(d)) {
        library(officer)
        doc <- read_docx()
        doc <- body_add_par(doc, "No conversation to export.", style = "Normal")
        print(doc, target = file)
        return()
      }
      tryCatch(save_docx(d$question, d$answer, d$sources, d$cfg, file),
               error = function(e) {
                 library(officer)
                 doc <- read_docx()
                 doc <- body_add_par(doc, paste("Export error:", conditionMessage(e)), style = "Normal")
                 print(doc, target = file)
               })
    }
  )

  # ── Council ──────────────────────────────────────────────────────────────────
  council_results <- reactiveVal(NULL)
  council_is_busy <- reactiveVal(FALSE)

  output$council_status <- renderUI({
    if (council_is_busy())
      tags$div(class = "status-bar", icon("spinner", class = "fa-spin"),
               " Consulting agents — this may take 30-60 seconds...")
  })

  observeEvent(input$council_run, {
    req(!council_is_busy())
    topic <- trimws(input$council_topic)
    if (nchar(topic) == 0) { showNotification("Please enter a topic.", type = "warning"); return() }
    sel <- input$council_agents
    if (length(sel) < 1) { showNotification("Select at least one agent.", type = "warning"); return() }

    council_results(NULL)
    council_is_busy(TRUE)

    responses <- list()
    for (org in sel) {
      cfg        <- AGENTS[[org]]
      chunks     <- KB_CACHE[[org]]
      top_chunks <- keyword_search(chunks, topic, top_k = 7)
      sources    <- vapply(top_chunks, function(c) c$source %||% "unknown", character(1))
      context    <- build_context(top_chunks)
      all_corr   <- load_corrections(org)
      rel_corr   <- find_relevant_corrections(all_corr, topic, top_k = 3)
      sys_prompt <- build_system_prompt(cfg, context, corrections = rel_corr)

      answer <- tryCatch(
        call_claude(api_key(), sys_prompt, list(list(role = "user", content = topic))),
        error = function(e) paste("Error:", conditionMessage(e))
      )
      responses[[org]] <- list(cfg = cfg, answer = answer, sources = sources)
    }

    synthesis <- NULL
    if (length(responses) > 1) {
      synthesis_ctx <- paste(sapply(names(responses), function(org) {
        r <- responses[[org]]
        paste0("### ", r$cfg$name_en %||% r$cfg$name, "\n", r$answer)
      }), collapse = "\n\n---\n\n")
      synth_system <- paste0(
        "You are a neutral policy rapporteur. You have statements from ",
        length(responses), " Israeli government agencies on one topic. ",
        "Write a concise synthesis: (1) key areas of agreement, ",
        "(2) tensions or differing emphases, (3) cross-cutting implications. ",
        "Be balanced, cite each institution by name, under 300 words. ",
        "Respond in the same language as the topic."
      )
      synthesis <- tryCatch(
        call_claude(api_key(), synth_system,
                    list(list(role = "user", content = paste0("Topic: ", topic,
                              "\n\nStatements:\n\n", synthesis_ctx))),
                    max_tokens = 1000),
        error = function(e) paste("Synthesis error:", conditionMessage(e))
      )
    }

    council_results(list(topic = topic, responses = responses, synthesis = synthesis))
    council_is_busy(FALSE)
  })

  output$council_output <- renderUI({
    res <- council_results()
    if (is.null(res)) return(NULL)

    cards <- lapply(names(res$responses), function(org) {
      r   <- res$responses[[org]]
      src <- if (length(r$sources) > 0)
        tags$p(class = "msg-sources",
               paste("Sources:", paste(unique(r$sources), collapse = " | ")))
      else NULL
      tags$div(class = "council-card",
        tags$h4(r$cfg$name_en %||% r$cfg$name),
        tags$p(style = "white-space:pre-wrap;", r$answer),
        src
      )
    })

    synth_ui <- if (!is.null(res$synthesis))
      tags$div(class = "synthesis-card",
        tags$h4(icon("balance-scale"), " Rapporteur Synthesis"),
        tags$p(style = "white-space:pre-wrap;", res$synthesis))

    tagList(
      tags$h4(style = "color:#1F497D;", "Topic: ", res$topic), hr(),
      do.call(tagList, cards), synth_ui
    )
  })

  output$council_export <- downloadHandler(
    filename = function() paste0("govpersona_council_", format(Sys.Date(), "%Y-%m-%d"), ".docx"),
    content  = function(file) {
      res <- council_results()
      if (is.null(res)) {
        library(officer); doc <- read_docx()
        doc <- body_add_par(doc, "No council session yet.", style = "Normal")
        print(doc, target = file); return()
      }
      library(officer)
      doc        <- read_docx()
      title_prop <- fp_text(font.size = 18, bold = TRUE, color = "#1F497D", font.family = "Calibri")
      h2_prop    <- fp_text(font.size = 14, bold = TRUE, color = "#1F497D", font.family = "Calibri")
      body_prop  <- fp_text(font.size = 11, font.family = "Calibri")
      src_prop   <- fp_text(font.size = 10, color = "#444", font.family = "Calibri")
      foot_prop  <- fp_text(font.size = 8, italic = TRUE, color = "#AAA", font.family = "Calibri")

      doc <- doc |>
        body_add_fpar(fpar(ftext("GovPersona — Council Session", title_prop))) |>
        body_add_fpar(fpar(ftext(format(Sys.Date(), "%B %d, %Y"),
                                 fp_text(font.size=10, color="#888", font.family="Calibri")))) |>
        body_add_par("", style="Normal") |>
        body_add_fpar(fpar(ftext("Topic", h2_prop))) |>
        body_add_fpar(fpar(ftext(res$topic,
                                 fp_text(font.size=12, italic=TRUE, font.family="Calibri")))) |>
        body_add_par("", style="Normal")

      for (org in names(res$responses)) {
        r <- res$responses[[org]]
        doc <- body_add_fpar(doc, fpar(ftext(r$cfg$name_en %||% r$cfg$name, h2_prop)))
        for (block in strsplit(r$answer, "\n\n")[[1]]) {
          block <- trimws(block)
          if (nchar(block) > 0) doc <- body_add_fpar(doc, fpar(ftext(block, body_prop)))
        }
        if (length(r$sources) > 0)
          doc <- body_add_fpar(doc, fpar(ftext(
            paste("Sources:", paste(unique(r$sources), collapse = " | ")), src_prop)))
        doc <- body_add_par(doc, "", style = "Normal")
      }

      if (!is.null(res$synthesis)) {
        doc <- body_add_fpar(doc, fpar(ftext("Rapporteur Synthesis", h2_prop)))
        for (block in strsplit(res$synthesis, "\n\n")[[1]]) {
          block <- trimws(block)
          if (nchar(block) > 0) doc <- body_add_fpar(doc, fpar(ftext(block, body_prop)))
        }
      }
      doc <- doc |> body_add_par("", style="Normal") |>
        body_add_fpar(fpar(ftext("Generated by GovPersona  |  Powered by Claude (Anthropic)", foot_prop)))
      print(doc, target = file)
    }
  )

  # ── Training tab ─────────────────────────────────────────────────────────────
  train_data <- reactive({
    input$train_refresh
    input$train_agent
    load_corrections(input$train_agent)
  })

  output$train_summary <- renderUI({
    corrs <- train_data()
    org   <- input$train_agent
    cfg   <- AGENTS[[org]]
    tags$div(
      style = "background:#fff; border:1px solid #dde3f0; border-radius:8px; padding:14px; margin-bottom:16px;",
      tags$h4(style = "color:#1F497D; margin-top:0;",
              icon("graduation-cap"), " ", cfg$name_en %||% cfg$name),
      tags$p(
        tags$b(format(length(corrs), big.mark=",")), " correction(s) saved. ",
        if (length(corrs) > 0)
          tags$span(style="color:#2d7a3a;",
                    "These are automatically applied to future questions.")
        else
          tags$span(style="color:#888;",
                    "No corrections yet. Use the Chat tab to correct answers.")
      )
    )
  })

  output$train_corrections_list <- renderUI({
    corrs <- train_data()
    if (length(corrs) == 0) return(NULL)

    tagList(
      tags$h5(style = "color:#555;", "Saved Corrections (newest first)"),
      lapply(rev(seq_along(corrs)), function(i) {
        c <- corrs[[i]]
        tags$div(class = "correction-card",
          tags$div(class = "correction-q", icon("question-circle"), " ", c$question),
          tags$div(style = "font-size:12px; color:#c0520a; margin:4px 0;",
                   icon("arrow-right"), " Corrected answer:"),
          tags$div(class = "correction-a", c$correction),
          tags$div(class = "correction-ts",
                   icon("clock"), " Saved: ", c$timestamp,
                   tags$button(
                     style = "margin-left:12px; background:#fee; border:1px solid #fcc;
                              border-radius:10px; padding:1px 8px; font-size:11px; cursor:pointer; color:#c00;",
                     onclick = paste0("Shiny.setInputValue('delete_correction_idx', ", i,
                                      ", {priority: 'event'})"),
                     "Delete"
                   ))
        )
      })
    )
  })

  observeEvent(input$delete_correction_idx, {
    idx <- input$delete_correction_idx
    org <- input$train_agent
    delete_correction(org, idx)
    showNotification("Correction deleted.", type = "message", duration = 3)
  })

  # ── Agents tab ───────────────────────────────────────────────────────────────
  output$agents_cards <- renderUI({
    lapply(names(AGENTS), function(org) {
      cfg        <- AGENTS[[org]]
      kb_count   <- length(KB_CACHE[[org]])
      corr_count <- length(load_corrections(org))
      tags$div(
        style = "background:#fff; border:1px solid #dde3f0; border-radius:8px;
                 padding:20px; margin-bottom:16px;",
        tags$h4(style = "color:#1F497D; margin-top:0;", cfg$name_en %||% cfg$name),
        tags$p(tags$b("Hebrew name: "), cfg$name_he %||% ""),
        tags$p(tags$b("Role: "), cfg$role_title),
        tags$p(tags$b("Mandate: "), cfg$org_mandate),
        tags$p(
          icon("database"), " KB: ",
          tags$b(format(kb_count, big.mark=",")), " chunks",
          if (kb_count == 0) tags$span(style="color:#888; margin-left:6px;",
                                       "(institutional knowledge only)")
        ),
        tags$p(
          icon("graduation-cap"), " Training: ",
          tags$b(corr_count), " correction(s)",
          if (corr_count > 0) tags$span(style="color:#2d7a3a; margin-left:6px;", "active")
        )
      )
    })
  })

  # JS helpers
  session$onFlushed(function() session$sendCustomMessage("scrollChat", list()), once = FALSE)
}

# =============================================================================
# Run
# =============================================================================
ui_final <- tagList(
  ui,
  tags$script(HTML("
    Shiny.addCustomMessageHandler('scrollChat', function(msg) {
      var el = document.getElementById('chat_box');
      if (el) el.scrollTop = el.scrollHeight;
    });
    Shiny.addCustomMessageHandler('refreshBadge', function(msg) {});
  "))
)

shinyApp(ui_final, server)
