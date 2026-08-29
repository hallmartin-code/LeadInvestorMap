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

.block-container{ padding-top:2.6rem; padding-bottom:3rem; max-width:1000px; }

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

.tc-card,
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .tc-card-marker){
  background: linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 100%);
  border:1px solid var(--navy-700);
  border-radius:20px;
  padding:40px 44px 34px;
  box-shadow:0 30px 60px -20px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.03);
  position:relative;
  overflow:hidden;
  margin-bottom:26px;
}
.tc-card::after,
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .tc-card-marker)::after{
  content:"";
  position:absolute; top:0; left:44px; right:44px; height:2px;
  background: linear-gradient(90deg, var(--coral), var(--amber), var(--teal));
  border-radius:2px;
}

.tc-eyebrow{
  display:flex; align-items:center; gap:8px;
  font-family:'JetBrains Mono', monospace; font-size:11px; letter-spacing:0.14em;
  text-transform:uppercase; color:var(--teal); margin-bottom:14px;
}
.tc-eyebrow::before{
  content:""; width:6px; height:6px; border-radius:50%;
  background:var(--teal); box-shadow:0 0 0 3px rgba(53,190,187,0.18);
}

.tc-card h1,
[data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .tc-card-marker) h1{
  font-size:28px; font-weight:700; line-height:1.25; margin:0 0 12px;
}
.tc-card-marker{ display:none; }
.tc-card h1 .arrow{ color:var(--ink-500); font-weight:400; margin:0 6px; }
.tc-card h1 .to{
  background: linear-gradient(90deg, var(--coral-soft), var(--amber));
  -webkit-background-clip:text; background-clip:text; color:transparent;
}
.tc-lede{ color:var(--ink-300); font-size:15px; line-height:1.6; margin:0; max-width:56ch; }

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
  padding:26px 22px;
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
[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderDropzone"] span{ color:var(--ink-500); }

/* --- buttons ---------------------------------------------------------------------- */

.stButton > button, .stDownloadButton > button{
  width:100%;
  border:none;
  border-radius:12px;
  padding:14px 20px;
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
  padding:14px 16px;
}
[data-testid="stMetricLabel"]{
  font-family:'JetBrains Mono', monospace; font-size:10px !important;
  letter-spacing:0.12em; text-transform:uppercase; color:var(--ink-500) !important;
}
[data-testid="stMetricValue"]{
  font-family:'Sora', sans-serif; font-size:18px !important; color:var(--ink-100) !important;
  /* A cheque range is wider than a stage name; let it wrap rather than be clipped. */
  white-space:normal; overflow-wrap:anywhere; line-height:1.25;
}

[data-testid="stDataFrame"]{ border:1px solid var(--navy-700); border-radius:12px; }

.stAlert{ border-radius:12px; border:1px solid var(--navy-700); }

hr{ border-color:var(--navy-700); }

/* --- disclosure and footer ------------------------------------------------------------ */

.tc-disclosure{
  margin-top:20px; padding-top:16px; border-top:1px solid var(--navy-700);
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
  .tc-card{ padding:30px 22px 26px; }
  .tc-card::after{ left:22px; right:22px; }
  .tc-card h1{ font-size:23px; }
}
</style>
""".replace("FONT_URL", FONTS)


# --- content that must track the application, not the markup -------------------------------


def deck_formats() -> str:
    """The deck types the ingestion layer actually reads."""
    return " ".join(sorted(e.lstrip(".") for e in DECK_EXTENSIONS))


def support_formats() -> str:
    return " ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS - DECK_EXTENSIONS))


def upload_limit() -> str:
    return f"up to {max_upload_mb()} MB"


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


def md_safe(text: str) -> str:
    """Escape dollar signs before text reaches Streamlit markdown.

    Streamlit reads ``$...$`` as LaTeX, so a cheque range like "$3.4M-$6.0M" renders as
    italic mathematics. Money is the one thing this application must never garble.
    """
    return str(text).replace("$", r"\$")


# --- components ------------------------------------------------------------------------------


def inject(st) -> None:
    """Apply the stylesheet. Call once, immediately after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)


def brand(st) -> None:
    st.markdown(
        f'<div class="tc-brand">{BRAND_MARK}<div class="tc-word">Ten Capital<span>Network</span></div></div>',
        unsafe_allow_html=True,
    )


def hero(st, *, eyebrow: str, title_lead: str, title_accent: str, lede: str) -> None:
    """The headline card: eyebrow, two-tone title, and one line of orientation."""
    st.markdown(
        f'<div class="tc-card">'
        f'<div class="tc-eyebrow">{eyebrow}</div>'
        f'<h1>{title_lead}<span class="arrow">&rarr;</span>'
        f'<span class="to">{title_accent}</span></h1>'
        f'<p class="tc-lede">{lede}</p>'
        f"</div>",
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
            header.append(f'<div class="tc-eyebrow">{eyebrow}</div>')
        if title:
            header.append(f"<h1>{title}</h1>")
        if lede:
            header.append(f'<p class="tc-lede">{lede}</p>')
        if header:
            st.markdown("".join(header), unsafe_allow_html=True)
        yield


def disclosure(st) -> None:
    st.markdown(f'<div class="tc-disclosure">{disclosure_html()}</div>', unsafe_allow_html=True)


def footer(st) -> None:
    st.markdown('<p class="tc-foot">Powered by TEN Capital Network</p>', unsafe_allow_html=True)
