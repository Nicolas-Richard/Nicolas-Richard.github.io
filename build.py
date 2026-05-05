import re
import shutil
from pathlib import Path
from datetime import datetime

import markdown
import yaml

POSTS_DIR = Path("posts")
SITE_DIR = Path("site")

HEADER = """\
<header>
  <a href="/" class="name">Nicolas Richard</a>
  <nav>
    <a href="https://github.com/Nicolas-Richard">GitHub</a>
    <a href="https://www.linkedin.com/in/nrichard1">LinkedIn</a>
  </nav>
</header>"""

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{css_path}style.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
</head>
<body>
{header}
<main>
{content}
</main>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: true }});
</script>
</body>
</html>"""


def parse_post(path):
    text = path.read_text()
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front)
    else:
        meta, body = {}, text

    date = meta.get("date")
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d")

    slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)

    return {
        "slug": slug,
        "title": meta.get("title", slug.replace("-", " ").title()),
        "date": date,
        "series": meta.get("series"),
        "tag": meta.get("tag"),
        "body": body.strip(),
    }


def fmt_date(d):
    return d.strftime("%d/%m/%Y")


def build():
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "posts").mkdir(exist_ok=True)
    shutil.copy("style.css", SITE_DIR / "style.css")

    posts = sorted(
        [parse_post(p) for p in POSTS_DIR.glob("*.md")],
        key=lambda p: p["date"],
        reverse=True,
    )

    # Copy assets
    if Path("assets").exists():
        shutil.copytree("assets", SITE_DIR / "assets", dirs_exist_ok=True)

    # Build series index: series -> posts ordered oldest first
    series_map = {}
    for p in sorted(posts, key=lambda p: p["date"]):
        if p["series"]:
            series_map.setdefault(p["series"], []).append(p)

    def post_nav(post):
        if not post["series"]:
            return ""
        siblings = series_map[post["series"]]
        idx = next(i for i, p in enumerate(siblings) if p["slug"] == post["slug"])
        prev = siblings[idx - 1] if idx > 0 else None
        nxt  = siblings[idx + 1] if idx < len(siblings) - 1 else None
        left  = f'<a href="/posts/{prev["slug"]}.html">← {prev["title"]}</a>' if prev else '<span></span>'
        right = f'<a href="/posts/{nxt["slug"]}.html">{nxt["title"]} →</a>' if nxt else '<span></span>'
        return f'<nav class="post-nav">{left}{right}</nav>'

    # Post pages
    for post in posts:
        body = re.sub(r'^#[^#].*\n', '', post["body"], count=1)
        body_html = markdown.markdown(body, extensions=["fenced_code", "tables"])
        # Let Mermaid JS render diagrams client-side
        body_html = re.sub(
            r'<pre><code class="language-mermaid">(.*?)</code></pre>',
            r'<pre class="mermaid">\1</pre>',
            body_html,
            flags=re.DOTALL,
        )
        nav = post_nav(post)
        content = f"""\
<article>
  {nav}
  <h1>{post["title"]}</h1>
  <time>{fmt_date(post["date"])}</time>
  <div class="content">{body_html}</div>
  {nav}
</article>"""
        html = PAGE.format(
            title=f'{post["title"]} — Nicolas Richard',
            css_path="/",
            header=HEADER,
            content=content,
        )
        (SITE_DIR / "posts" / f'{post["slug"]}.html').write_text(html)

    # Index
    def series_tag(p):
        label = p["series"] or p["tag"]
        if label:
            return f'<span class="series-tag">{label}</span>'
        return ""

    items = "\n".join(
        f'  <li>'
        f'<span class="date">{fmt_date(p["date"])}</span>'
        f'<span class="series-col">{series_tag(p)}</span>'
        f'<a href="/posts/{p["slug"]}.html">{p["title"]}</a>'
        f'</li>'
        for p in posts
    )
    content = f'<ul class="posts">\n{items}\n</ul>'
    html = PAGE.format(
        title="Nicolas Richard",
        css_path="/",
        header=HEADER,
        content=content,
    )
    (SITE_DIR / "index.html").write_text(html)

    print(f"Built {len(posts)} post(s) → {SITE_DIR}/")


if __name__ == "__main__":
    build()
