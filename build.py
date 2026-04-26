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
</head>
<body>
{header}
<main>
{content}
</main>
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
        "body": body.strip(),
    }


def fmt_date(d):
    return d.strftime("%B %-d, %Y")


def build():
    SITE_DIR.mkdir(exist_ok=True)
    (SITE_DIR / "posts").mkdir(exist_ok=True)
    shutil.copy("style.css", SITE_DIR / "style.css")

    posts = sorted(
        [parse_post(p) for p in POSTS_DIR.glob("*.md")],
        key=lambda p: p["date"],
        reverse=True,
    )

    # Post pages
    for post in posts:
        body_html = markdown.markdown(post["body"], extensions=["fenced_code", "tables"])
        content = f"""\
<article>
  <h1>{post["title"]}</h1>
  <time>{fmt_date(post["date"])}</time>
  <div class="content">{body_html}</div>
</article>"""
        html = PAGE.format(
            title=f'{post["title"]} — Nicolas Richard',
            css_path="/",
            header=HEADER,
            content=content,
        )
        (SITE_DIR / "posts" / f'{post["slug"]}.html').write_text(html)

    # Index
    items = "\n".join(
        f'  <li>'
        f'<span class="date">{fmt_date(p["date"])}</span>'
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
