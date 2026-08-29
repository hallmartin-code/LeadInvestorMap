"""TEN Capital screen styling for the Streamlit app.

The design is the supplied one-pager mockup: a dark navy ground, a single raised card
with a coral-amber-teal hairline across its top, Sora for headings, Inter for body, and
JetBrains Mono for the technical asides. The tri-colour palette echoes the three figures
in the brand mark.

Two rules govern what is here:

* **The screen is dark; the deliverable is not.** The one-page PDF stays white and
  institutional because it is printed, forwarded and read in committee. Restyling the PDF
  to match the UI would make it worse at its job.
* **The chrome never claims more than the application does.** Accepted file types, the
  size ceiling and the notification address are all read from configuration rather than
  written into the markup, so the page cannot promise something the app will refuse.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from ..ingestion.loader import DECK_EXTENSIONS, SUPPORTED_EXTENSIONS
from ..utils.config import EmailSettings, max_upload_mb

FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&"
    "family=JetBrains+Mono:wght@400;500&display=swap"
)

#: The brand mark: three figures, one per accent colour.
BRAND_MARK = """
<svg class="tc-mark" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"
     role="img" aria-label="TEN Capital Network">
  <path d="M50 6 C64 6 74 16 74 16" stroke="var(--amber)" stroke-width="11"
        stroke-linecap="round" fill="none"/>
  <path d="M76 66 C76 82 63 92 63 92" stroke="var(--teal)" stroke-width="11"
        stroke-linecap="round" fill="none"/>
  <path d="M24 66 C24 82 37 92 37 92" stroke="var(--coral)" stroke-width="11"
        stroke-linecap="round" fill="none" transform="rotate(180 50 79)"/>
  <circle cx="50" cy="20" r="11" fill="var(--amber)"/>
  <circle cx="78" cy="68" r="11" fill="var(--teal)"/>
  <circle cx="22" cy="68" r="11" fill="var(--coral)"/>
</svg>
"""

#: A Streamlit widget cannot live inside an injected <div>, so the card is a bordered
#: st.container matched by a marker inside it. The selector is written once here and
#: substituted into the stylesheet rather than repeated at every rule that needs it.
CARD = (
    '[data-testid="stVerticalBlock"]'
    ':has(> [data-testid="stElementContainer"] .tc-card-marker)'
)

CSS = """
<style>
@import url('FONT_URL');

:root{
  --navy-950:#0B1526;
  --navy-900:#101E33;
  --navy-800:#16283F;
  --navy-700:#1E354F;
  --coral:#EE5A4E;
  --coral-soft:#F0776C;
  --amber:#F3A22A;
  --teal:#35BEBB;
  --ink-100:#F3F6FA;
  --ink-300:#C4D0E0;
  --ink-500:#7E90A8;
  --ink-600:#5C6E86;
}

/* --- ground -------------------------------------------------------------------- */

.stApp{
  background: var(--navy-950);
  color: var(--ink-100);
  font-family:'Inter', sans-serif;
}

/* The ambient tri-colour glow, echoing the mark. Fixed so it does not scroll away. */
.stApp::before{
  content:"";
  position:fixed;
  inset:0;
  background:
    radial-gradient(480px 380px at 14% 8%, rgba(238,90,78,0.16), transparent 60%),
    radial-gradient(480px 380px at 86% 6%, rgba(243,162,42,0.13), transparent 60%),
    radial-gradient(560px 420px at 50% 100%, rgba(53,190,187,0.14), transparent 60%);
  pointer-events:none;
  z-index:0;
}
.stApp > *{ position:relative; z-index:1; }

.block-container{
  padding-top:2.6rem; padding-bottom:3rem;
  max-width:1000px;
  /* The mockup is one centred column; a max-width on its own would pin it left. */
  margin-left:auto; margin-right:auto;
}

/* Streamlit ships its own font rules; these are deliberately specific enough to win
   rather than relying on source order. */
.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp .tc-word, .stApp .tc-card h1{
  font-family:'Sora', sans-serif !important;
  letter-spacing:-0.01em;
  color:var(--ink-100);
}
.stApp, .stApp p, .stApp li, .stApp label, .stApp .tc-lede{
  font-family:'Inter', sans-serif !important;
}
.stApp .tc-eyebrow, .stApp .tc-foot, .stApp .tc-disclosure code,
.stApp [data-testid="stFileUploader"] label, .stApp [data-testid="stMetricLabel"]{
  font-family:'JetBrains Mono', monospace !important;
}

p, li, label, span, div{ color:var(--ink-300); }

/* --- brand lockup --------------------------------------------------------------- */

.tc-brand{ display:flex; align-items:center; gap:12px; margin:0 0 26px; }
.tc-mark{ width:34px; height:34px; flex-shrink:0; }
.tc-word{
  font-family:'Sora', sans-serif; font-weight:800; font-size:15px;
  letter-spacing:0.04em; line-height:1.15; color:var(--ink-100); text-transform:uppercase;
}
.tc-word span{
  display:block; font-weight:600; font-size:10px; letter-spacing:0.22em;
  color:var(--ink-500); margin-top:2px;
}

/* --- card ----------------------------------------------------------------------- */

%CARD%{
  background: linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 100%);
  border:1px solid var(--navy-700);
  border-radius:20px;
  padding:44px 44px 36px;
  box-shadow:0 30px 60px -20px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.03);
  position:relative;
  overflow:hidden;
  margin-bottom:26px;
}
%CARD%::after{
  content:"";
  position:absolute; top:0; left:44px; right:44px; height:2px;
  background: linear-gradient(90deg, var(--coral), var(--amber), var(--teal));
  border-radius:2px;
}

.tc-eyebrow{
  display:flex; align-items:center; gap:8px;
  font-family:'JetBrains Mono', monospace; font-size:11px; font-weight:500;
  letter-spacing:0.14em;
  text-transform:uppercase; color:var(--teal); margin:0 0 14px;
}
.tc-eyebrow::before{
  content:""; width:6px; height:6px; border-radius:50%; flex-shrink:0;
  background:var(--teal); box-shadow:0 0 0 3px rgba(53,190,187,0.18);
}

/* Half the width cannot carry the full inset. */
[data-testid="stColumn"] %CARD%{ padding:28px 28px 24px; }
[data-testid="stColumn"] %CARD%::after{ left:28px; right:28px; }

%CARD% h1{ font-size:28px; font-weight:700; line-height:1.25; margin:0 0 12px; }
.tc-card-marker{ display:none; }
h1 .arrow{ color:var(--ink-500); font-weight:400; margin:0 4px; }
h1 .to{
  background: linear-gradient(90deg, var(--coral-soft), var(--amber));
  -webkit-background-clip:text; background-clip:text; color:transparent;
}
/* Clipping the gradient to the glyphs leaves the text invisible where the property is
   unsupported, so the accent colour is restored rather than the heading disappearing. */
@supports not ((background-clip:text) or (-webkit-background-clip:text)){
  h1 .to{ color:var(--coral-soft); }
}
.tc-lede{ color:var(--ink-300); font-size:15px; line-height:1.6; margin:0 0 6px; max-width:56ch; }

/* --- upload zones ---------------------------------------------------------------- */

[data-testid="stFileUploader"] label{
  font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:0.12em;
  text-transform:uppercase; color:var(--ink-500);
}
[data-testid="stFileUploader"] label p{ color:var(--ink-500); }
[data-testid="stFileUploaderDropzone"]{
  border:1.5px dashed var(--navy-700);
  border-radius:14px;
  background:rgba(255,255,255,0.015);
  padding:24px 22px;
  transition:border-color .18s ease, background .18s ease;
}
[data-testid="stFileUploaderDropzone"]:hover{
  border-color:var(--teal);
  background:rgba(53,190,187,0.05);
}
[data-testid="stFileUploaderDropzone"]:focus-within{
  border-color:var(--teal);
  box-shadow:0 0 0 3px rgba(53,190,187,0.22);
}
[data-testid="stFileUploaderDropzone"] button{
  background:transparent;
  border:1px solid var(--navy-700);
  color:var(--ink-100);
  border-radius:9px;
  font-family:'Inter', sans-serif; font-weight:600;
}
[data-testid="stFileUploaderDropzone"] button:hover{
  border-color:var(--teal); color:var(--ink-100);
}
[data-testid="stFileUploaderDropzone"] span{ color:var(--ink-500); }
/* Streamlit prints the accepted types and the size ceiling inside every dropzone, and
   truncates the longer list to an ellipsis. The page says it once instead, under both
   zones and in full, in the mockup's mono sub-line - see hint(). */
[data-testid="stFileUploaderDropzoneInstructions"]{ display:none; }

.tc-hint{
  font-family:'JetBrains Mono', monospace !important;
  font-size:11.5px; letter-spacing:0.01em; color:var(--ink-500);
  margin:10px 2px 0;
}
.tc-hint b{ color:var(--ink-300); font-weight:500; }

/* --- buttons ---------------------------------------------------------------------- */

/* Streamlit sizes a button's container to its label unless the widget asks to stretch;
   the buttons here pass width="stretch", and this fills that container. */
.stButton > button, .stDownloadButton > button{
  width:100%;
  border:none;
  border-radius:12px;
  padding:16px 20px;
  font-family:'Sora', sans-serif; font-weight:700; font-size:15px;
  transition:filter .15s ease, transform .15s ease;
}
.stButton > button[kind="primary"]{
  background:linear-gradient(90deg, var(--coral) 0%, var(--coral-soft) 45%, var(--amber) 100%);
  color:#17130E;
  box-shadow:0 10px 24px -10px rgba(238,90,78,0.45);
}
.stButton > button[kind="primary"]:hover{ filter:brightness(1.06); transform:translateY(-1px); }
.stButton > button[kind="primary"]:active{ transform:translateY(0); }
/* The button is disabled until a deck is chosen. The gradient reads as "ready", so it
   has to be visibly withdrawn or the page invites a click it will refuse. */
.stButton > button[kind="primary"]:disabled,
.stButton > button[kind="primary"]:disabled:hover{
  background:rgba(255,255,255,0.04);
  color:var(--ink-600);
  box-shadow:none;
  filter:none;
  transform:none;
  cursor:not-allowed;
}
.stButton > button[kind="primary"]:focus-visible,
.stDownloadButton > button:focus-visible{
  outline:2px solid var(--teal); outline-offset:2px;
}
.stButton > button[kind="secondary"], .stDownloadButton > button{
  background:rgba(255,255,255,0.03);
  border:1px solid var(--navy-700);
  color:var(--ink-100);
  font-size:13px;
}
.stDownloadButton > button:hover{ border-color:var(--teal); filter:brightness(1.08); }

/* --- sidebar ----------------------------------------------------------------------- */

[data-testid="stSidebar"]{
  background:var(--navy-900);
  border-right:1px solid var(--navy-700);
}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3{
  font-family:'Sora', sans-serif; font-size:13px; letter-spacing:0.08em;
  text-transform:uppercase; color:var(--ink-500);
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div{
  background:var(--navy-950);
  border:1px solid var(--navy-700);
  color:var(--ink-100);
  border-radius:9px;
}
[data-testid="stSidebar"] .stTextInput input:focus{
  border-color:var(--teal); box-shadow:0 0 0 3px rgba(53,190,187,0.18);
}

/* --- results ------------------------------------------------------------------------ */

[data-testid="stMetric"]{
  background:rgba(255,255,255,0.02);
  border:1px solid var(--navy-700);
  border-radius:12px;
  padding:14px 14px;
  /* A wrapped cheque range makes one tile taller than its neighbours; stretching them
     keeps the row a row. The same rule squares up two cards sitting side by side. */
  height:100%;
}
/* Streamlit stretches the columns themselves but not what sits inside them, so a metric
   whose value wraps to two lines leaves its neighbours short and the row ragged. The
   height is handed down the chain to the tile. Cards in columns are deliberately left
   alone: stretching a short one to match a long list is a hole, not an alignment. */
[data-testid="stColumn"]{ display:flex; flex-direction:column; }
[data-testid="stColumn"]:has([data-testid="stMetric"]) > [data-testid="stVerticalBlock"],
[data-testid="stColumn"] [data-testid="stElementContainer"]:has(> [data-testid="stMetric"]){
  flex:1 1 auto;
}
[data-testid="stMetricLabel"]{
  font-family:'JetBrains Mono', monospace; font-size:10px !important;
  letter-spacing:0.12em; text-transform:uppercase; color:var(--ink-500) !important;
}
[data-testid="stMetricValue"]{
  font-family:'Sora', sans-serif; font-size:18px !important; color:var(--ink-100) !important;
  line-height:1.25;
}
/* A cheque range is the widest thing on the row and the first thing Streamlit ellipsises,
   so the one-line clamp is lifted from both the label and the value. Money that reads
   "$3.4M-$6..." is worse than money on two lines. */
[data-testid="stMetricLabel"], [data-testid="stMetricValue"],
[data-testid="stMetricLabel"] > div, [data-testid="stMetricValue"] > div,
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricValue"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMetricValue"] [data-testid="stMarkdownContainer"] p{
  white-space:normal;
  overflow:visible;
  text-overflow:clip;
  overflow-wrap:anywhere;
}

[data-testid="stDataFrame"]{ border:1px solid var(--navy-700); border-radius:12px; }

.stAlert{ border-radius:12px; border:1px solid var(--navy-700); }

hr{ border-color:var(--navy-700); }

/* --- disclosure and footer ------------------------------------------------------------ */

.tc-disclosure{
  margin-top:22px; padding-top:18px; border-top:1px solid var(--navy-700);
  font-size:12px; line-height:1.6; color:var(--ink-500);
}
.tc-disclosure code{
  font-family:'JetBrains Mono', monospace;
  background:var(--navy-950); border:1px solid var(--navy-700); color:var(--ink-300);
  padding:2px 6px; border-radius:5px; font-size:11.5px;
}
.tc-foot{
  text-align:center; margin:26px 0 0;
  font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:0.08em;
  color:var(--ink-600); text-transform:uppercase;
}

/* Streamlit's own chrome is noise here. */
#MainMenu, footer, [data-testid="stDecoration"]{ visibility:hidden; }

@media (prefers-reduced-motion: reduce){
  *{ transition:none !important; animation:none !important; }
  .stButton > button[kind="primary"]:hover{ transform:none; }
}

@media (max-width:640px){
  %CARD%{ padding:30px 22px 26px; }
  %CARD%::after{ left:22px; right:22px; }
  %CARD% h1{ font-size:23px; }
}
</style>
""".replace("FONT_URL", FONTS).replace("%CARD%", CARD)


# --- favicon -----------------------------------------------------------------------------

#: The project's public directory. Streamlit serves it at /app/static when
#: enableStaticServing is on, which is how the browser reaches these files.
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
STATIC_URL = "/app/static"

FAVICON_PNG = STATIC_DIR / "favicon.png"
FAVICON_ICO = STATIC_DIR / "favicon.ico"
APPLE_TOUCH_ICON = STATIC_DIR / "apple-touch-icon.png"


def page_icon():
    """The tab icon for st.set_page_config.

    Streamlit accepts a path or a PIL image. If the file is missing for any reason the
    app must still start, so this falls back to an emoji rather than raising at import.
    """
    return str(FAVICON_PNG) if FAVICON_PNG.exists() else ":bar_chart:"


def favicon_links() -> str:
    """Explicit icon links.

    Streamlit sets its own favicon from page_icon, but that single PNG does not cover the
    .ico that some browsers and Windows pinned tabs still ask for, nor the iOS
    home-screen icon. These are additive and harmless where unused.
    """
    return (
        f'<link rel="icon" type="image/png" sizes="512x512" href="{STATIC_URL}/favicon.png">'
        f'<link rel="alternate icon" type="image/x-icon" href="{STATIC_URL}/favicon.ico">'
        f'<link rel="apple-touch-icon" sizes="180x180" href="{STATIC_URL}/apple-touch-icon.png">'
    )


# --- content that must track the application, not the markup -------------------------------


#: A deck is a presentation or its PDF. Supporting material is everything else the
#: loader reads, plus PDF - research memos and diligence documents arrive that way - but
#: not a slide deck, which belongs in the deck slot where it is parsed as one.
DECK_TYPES = tuple(sorted(e.lstrip(".") for e in DECK_EXTENSIONS))
SUPPORT_TYPES = tuple(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS - {".ppt", ".pptx"}))


def deck_formats() -> str:
    """The deck types the ingestion layer actually reads."""
    return " ".join(DECK_TYPES)


def support_formats() -> str:
    return " ".join(SUPPORT_TYPES)


def upload_limit(megabytes: int | None = None) -> str:
    """The size ceiling, in words.

    The caller passes the live server limit where it can read one, because that is the
    number the browser will actually enforce; the configured value is the fallback.
    """
    return f"up to {megabytes or max_upload_mb()} MB"


def disclosure_html() -> str:
    """State what actually happens to the upload, including where it is sent.

    The address is read from configuration, and the sentence about email only appears when
    email is genuinely switched on - a promise the app would not keep is worse than none.
    """
    base = (
        "Uploaded files are processed on the server and discarded when the session ends; "
        "download anything you need to keep."
    )
    settings = EmailSettings.from_env()
    if settings.available and settings.enabled:
        return f"{base} A copy of every generated map is emailed to <code>{settings.default_to}</code>."
    return base


def two_tone(lead: str, accent: str) -> str:
    """The mockup's headline: plain lead, arrow, gradient accent. Pass to card(title=...)."""
    return f'{lead}<span class="arrow">&rarr;</span><span class="to">{accent}</span>'


def md_safe(text: str) -> str:
    """Escape dollar signs before text reaches Streamlit markdown.

    Streamlit reads ``$...$`` as LaTeX, so a cheque range like "$3.4M-$6.0M" renders as
    italic mathematics. Money is the one thing this application must never garble.
    """
    return str(text).replace("$", r"\$")


# --- components ------------------------------------------------------------------------------


def inject(st) -> None:
    """Apply the stylesheet and icon links. Call once, immediately after set_page_config.

    The stylesheet goes through ``st.html``, not ``st.markdown``. Markdown treats the
    injected string as a raw HTML block that *ends at the first blank line*, so everything
    in the stylesheet after that blank line was parsed as prose and printed on the page as
    visible CSS text. ``st.html`` is not markdown-parsed - the style element survives whole,
    and Streamlit routes style-only content to the event container so it takes no layout
    space. The icon links stay on ``st.markdown``: they are a single line with no blank
    line to trip over, and ``st.html`` sanitisation drops <link>.
    """
    st.markdown(favicon_links(), unsafe_allow_html=True)
    st.html(CSS)


def brand(st) -> None:
    st.markdown(
        f'<div class="tc-brand">{BRAND_MARK}<div class="tc-word">Ten Capital<span>Network</span></div></div>',
        unsafe_allow_html=True,
    )


@contextmanager
def card(st, *, eyebrow: str = "", title: str = "", lede: str = ""):
    """A TEN Capital card that really contains what is written inside it.

    An injected <div> cannot wrap Streamlit widgets - each widget is rendered into its own
    container, so the div closes immediately and the widgets fall outside the card. A
    bordered st.container is real DOM, so the card is styled by matching a marker inside
    it with :has(), which keeps the selector off Streamlit's generated class names.
    """
    with st.container(border=True):
        st.markdown('<span class="tc-card-marker"></span>', unsafe_allow_html=True)
        header = []
        if eyebrow:
            # With a title above it the eyebrow is a kicker; on its own it is the section
            # heading, so it is announced as one. It stays a <div> either way: Streamlit's
            # own heading rules are more specific than anything a class here can say, and
            # an <h2> would come out at 36px in the brand's 11px eyebrow face.
            role = "" if title else ' role="heading" aria-level="2"'
            header.append(f'<div class="tc-eyebrow"{role}>{eyebrow}</div>')
        if title:
            header.append(f"<h1>{title}</h1>")
        if lede:
            header.append(f'<p class="tc-lede">{lede}</p>')
        if header:
            st.markdown("".join(header), unsafe_allow_html=True)
        yield


def hint(st, limit_mb: int | None = None) -> None:
    """The mockup's dropzone sub-line: what the parsers read, and the real size ceiling.

    Streamlit prints its own copy of this inside every dropzone; the stylesheet hides it so
    the page says it once, in the mockup's typography, from the values the app itself uses.
    """
    st.markdown(
        f'<p class="tc-hint">deck <b>{deck_formats()}</b>'
        f"&nbsp;&middot;&nbsp; material <b>{support_formats()}</b>"
        f"&nbsp;&middot;&nbsp; {upload_limit(limit_mb)} per file</p>",
        unsafe_allow_html=True,
    )


def disclosure(st) -> None:
    st.markdown(f'<div class="tc-disclosure">{disclosure_html()}</div>', unsafe_allow_html=True)


def footer(st) -> None:
    st.markdown('<p class="tc-foot">Powered by TEN Capital Network</p>', unsafe_allow_html=True)
