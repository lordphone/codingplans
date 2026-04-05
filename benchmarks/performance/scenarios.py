"""
Realistic coding session scenarios for TPS benchmarking.

Provides system prompts, coding task prompts, and HTTP headers that make
benchmark requests resemble genuine IDE coding sessions from tools like
Cursor, Claude Code, Codex, and OpenCode.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    """A single benchmark scenario with full message context and headers."""

    name: str
    client: str
    messages: tuple[dict[str, str], ...]
    extra_headers: dict[str, str]


# ---------------------------------------------------------------------------
# Client header profiles
# ---------------------------------------------------------------------------

_CLIENTS: dict[str, dict[str, str]] = {
    "cursor": {
        "User-Agent": "connect-es/1.6.1",
    },
    "claude-code": {
        "User-Agent": "claude-cli/2.1.90 (external, cli)",
    },
    "codex": {
        "User-Agent": "codex-cli/1.0.3",
    },
    "opencode": {
        "User-Agent": "opencode/1.2.15",
    },
    "copilot": {
        "User-Agent": "GitHubCopilotChat/0.37.2026011603",
        "Editor-Version": "vscode/1.98.0",
    },
}

# ---------------------------------------------------------------------------
# System prompt styles (original but structurally similar to real tools)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS: dict[str, str] = {
    "ide": (
        "You are an AI coding assistant integrated into the user's code editor. "
        "Help with code generation, debugging, refactoring, and explanation. "
        "Provide concise, working code that follows the project's existing conventions. "
        "When modifying existing code, preserve the original style and formatting. "
        "Use the same programming language as the surrounding context unless asked otherwise. "
        "Include explanations only when the approach is non-obvious or the user asks for them. "
        "Prefer practical, production-ready solutions over toy examples."
    ),
    "cli": (
        "You are a coding agent running in a terminal-based coding assistant. "
        "You help developers write code, debug issues, and refactor projects.\n\n"
        "Be precise and direct. Avoid unnecessary preamble. "
        "Produce complete, runnable solutions rather than fragments. "
        "Consider edge cases and error handling in every solution. "
        "When multiple approaches exist, choose the most maintainable one."
    ),
    "chat": (
        "You are a pair programming assistant. The developer shares code with you "
        "and you help write, review, and improve it.\n\n"
        "Lead with the most relevant code changes. "
        "Use markdown code blocks with language identifiers. "
        "Keep explanations brief and actionable. "
        "Match the existing codebase patterns and conventions."
    ),
}

# ---------------------------------------------------------------------------
# Coding scenarios
# ---------------------------------------------------------------------------

_RAW_SCENARIOS: list[dict] = [
    {
        "name": "python_async_refactor",
        "system": "ide",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Refactor this synchronous HTTP client to use async/await with aiohttp:\n\n"
                    "```python\n"
                    "import requests\n\n"
                    "class DataFetcher:\n"
                    "    def __init__(self, base_url, api_key):\n"
                    "        self.base_url = base_url\n"
                    "        self.session = requests.Session()\n"
                    "        self.session.headers['Authorization'] = f'Bearer {api_key}'\n\n"
                    "    def get_users(self, page=1):\n"
                    "        resp = self.session.get(f'{self.base_url}/users', params={'page': page})\n"
                    "        resp.raise_for_status()\n"
                    "        return resp.json()\n\n"
                    "    def get_user_details(self, user_id):\n"
                    "        resp = self.session.get(f'{self.base_url}/users/{user_id}')\n"
                    "        resp.raise_for_status()\n"
                    "        return resp.json()\n\n"
                    "    def fetch_all_users(self):\n"
                    "        all_users = []\n"
                    "        page = 1\n"
                    "        while True:\n"
                    "            data = self.get_users(page)\n"
                    "            if not data['results']:\n"
                    "                break\n"
                    "            all_users.extend(data['results'])\n"
                    "            page += 1\n"
                    "        return all_users\n"
                    "```\n\n"
                    "Use proper async context management and add retry logic with exponential backoff."
                ),
            },
        ],
    },
    {
        "name": "typescript_race_condition",
        "system": "cli",
        "turns": [
            {
                "role": "user",
                "content": (
                    "This React hook has a race condition when the query changes rapidly. "
                    "Fix it and explain the issue:\n\n"
                    "```typescript\n"
                    "function useSearch(query: string) {\n"
                    "  const [results, setResults] = useState<SearchResult[]>([]);\n"
                    "  const [loading, setLoading] = useState(false);\n\n"
                    "  useEffect(() => {\n"
                    "    if (!query) {\n"
                    "      setResults([]);\n"
                    "      return;\n"
                    "    }\n"
                    "    setLoading(true);\n"
                    "    fetch(`/api/search?q=${encodeURIComponent(query)}`)\n"
                    "      .then(res => res.json())\n"
                    "      .then(data => {\n"
                    "        setResults(data.results);\n"
                    "        setLoading(false);\n"
                    "      });\n"
                    "  }, [query]);\n\n"
                    "  return { results, loading };\n"
                    "}\n"
                    "```"
                ),
            },
        ],
    },
    {
        "name": "python_test_generation",
        "system": "chat",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Write comprehensive pytest tests for this data validation module:\n\n"
                    "```python\n"
                    "from dataclasses import dataclass\n"
                    "from datetime import datetime\n"
                    "from typing import Optional\n\n\n"
                    "@dataclass\n"
                    "class UserProfile:\n"
                    "    username: str\n"
                    "    email: str\n"
                    "    age: Optional[int] = None\n"
                    "    created_at: Optional[datetime] = None\n\n\n"
                    "class ValidationError(Exception):\n"
                    "    def __init__(self, field: str, message: str):\n"
                    "        self.field = field\n"
                    "        self.message = message\n"
                    "        super().__init__(f\"{field}: {message}\")\n\n\n"
                    "def validate_profile(profile: UserProfile) -> list[str]:\n"
                    "    errors = []\n"
                    "    if not profile.username or len(profile.username) < 3:\n"
                    "        errors.append('Username must be at least 3 characters')\n"
                    "    if len(profile.username) > 30:\n"
                    "        errors.append('Username must be at most 30 characters')\n"
                    "    if not profile.email or '@' not in profile.email:\n"
                    "        errors.append('Invalid email address')\n"
                    "    if profile.age is not None and (profile.age < 0 or profile.age > 150):\n"
                    "        errors.append('Age must be between 0 and 150')\n"
                    "    return errors\n"
                    "```\n\n"
                    "Cover edge cases, boundary values, and error paths."
                ),
            },
        ],
    },
    {
        "name": "go_worker_pool",
        "system": "cli",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Implement a generic concurrent worker pool in Go with these requirements:\n"
                    "- Configurable number of workers\n"
                    "- Buffered input and output channels\n"
                    "- Graceful shutdown via context cancellation\n"
                    "- Error collection without stopping other workers\n"
                    "- Use generics (Go 1.21+)\n\n"
                    "Here's the interface I want to implement:\n\n"
                    "```go\n"
                    "type Pool[In, Out any] struct {\n"
                    "    workers  int\n"
                    "    process  func(context.Context, In) (Out, error)\n"
                    "}\n\n"
                    "type Result[T any] struct {\n"
                    "    Value T\n"
                    "    Err   error\n"
                    "}\n"
                    "```\n\n"
                    "Include a usage example with HTTP request processing."
                ),
            },
        ],
    },
    {
        "name": "python_sql_optimization",
        "system": "ide",
        "turns": [
            {
                "role": "user",
                "content": (
                    "This function has N+1 query problems and is very slow with large datasets. "
                    "Optimize it using SQLAlchemy best practices:\n\n"
                    "```python\n"
                    "def get_order_summaries(session, customer_id):\n"
                    "    customer = session.query(Customer).get(customer_id)\n"
                    "    summaries = []\n"
                    "    for order in customer.orders:\n"
                    "        items = []\n"
                    "        for item in order.items:\n"
                    "            product = session.query(Product).get(item.product_id)\n"
                    "            items.append({\n"
                    "                'product_name': product.name,\n"
                    "                'quantity': item.quantity,\n"
                    "                'subtotal': item.quantity * product.price,\n"
                    "            })\n"
                    "        summaries.append({\n"
                    "            'order_id': order.id,\n"
                    "            'date': order.created_at,\n"
                    "            'total': sum(i['subtotal'] for i in items),\n"
                    "            'items': items,\n"
                    "        })\n"
                    "    return summaries\n"
                    "```\n\n"
                    "Use eager loading and minimize database round trips."
                ),
            },
        ],
    },
    {
        "name": "typescript_pagination",
        "system": "chat",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Add cursor-based pagination to this API client. "
                    "I need both forward and backward pagination:\n\n"
                    "```typescript\n"
                    "interface ApiClient {\n"
                    "  baseUrl: string;\n"
                    "  headers: Record<string, string>;\n"
                    "}\n\n"
                    "interface ListResponse<T> {\n"
                    "  data: T[];\n"
                    "  total: number;\n"
                    "}\n\n"
                    "async function listItems<T>(\n"
                    "  client: ApiClient,\n"
                    "  endpoint: string,\n"
                    "): Promise<T[]> {\n"
                    "  const res = await fetch(`${client.baseUrl}${endpoint}`, {\n"
                    "    headers: client.headers,\n"
                    "  });\n"
                    "  const json: ListResponse<T> = await res.json();\n"
                    "  return json.data;\n"
                    "}\n"
                    "```\n\n"
                    "The API supports `cursor`, `limit`, and `direction` query params."
                ),
            },
        ],
    },
    {
        "name": "python_error_handling",
        "system": "ide",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Add proper error handling, logging, and retry logic to this file processor:\n\n"
                    "```python\n"
                    "import csv\n"
                    "import json\n\n"
                    "def process_data_file(input_path, output_path, transform_fn):\n"
                    "    with open(input_path) as f:\n"
                    "        reader = csv.DictReader(f)\n"
                    "        results = []\n"
                    "        for row in reader:\n"
                    "            transformed = transform_fn(row)\n"
                    "            results.append(transformed)\n"
                    "    with open(output_path, 'w') as f:\n"
                    "        json.dump(results, f, indent=2)\n"
                    "    return len(results)\n"
                    "```\n\n"
                    "Use the logging module, handle file not found, permission errors, "
                    "malformed CSV rows, and transform function failures. "
                    "Each failed row should be logged and skipped, not crash the whole process."
                ),
            },
        ],
    },
    {
        "name": "rust_from_python",
        "system": "cli",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Convert this Python text processing pipeline to Rust. "
                    "Focus on correctness and idiomatic Rust:\n\n"
                    "```python\n"
                    "import re\n"
                    "from collections import Counter\n\n"
                    "def analyze_text(text: str) -> dict:\n"
                    "    words = re.findall(r'\\\\b[a-zA-Z]+\\\\b', text.lower())\n"
                    "    word_counts = Counter(words)\n"
                    "    total = len(words)\n"
                    "    unique = len(word_counts)\n"
                    "    top_10 = word_counts.most_common(10)\n"
                    "    avg_len = sum(len(w) for w in words) / max(total, 1)\n"
                    "    return {\n"
                    "        'total_words': total,\n"
                    "        'unique_words': unique,\n"
                    "        'avg_word_length': round(avg_len, 2),\n"
                    "        'top_words': dict(top_10),\n"
                    "        'lexical_diversity': round(unique / max(total, 1), 4),\n"
                    "    }\n"
                    "```\n\n"
                    "Use standard library where possible. Return a struct, not a HashMap."
                ),
            },
        ],
    },
    {
        "name": "python_auth_multiturn",
        "system": "chat",
        "turns": [
            {
                "role": "user",
                "content": (
                    "I'm building a FastAPI app and need to add JWT authentication. "
                    "Here's my current app structure:\n\n"
                    "```python\n"
                    "from fastapi import FastAPI, Depends\n"
                    "from sqlalchemy.orm import Session\n\n"
                    "app = FastAPI()\n\n"
                    "@app.get('/users/me')\n"
                    "def get_current_user(db: Session = Depends(get_db)):\n"
                    "    pass\n\n"
                    "@app.post('/users')\n"
                    "def create_user(user: UserCreate, db: Session = Depends(get_db)):\n"
                    "    pass\n"
                    "```\n\n"
                    "Can you implement the auth middleware with login and token refresh?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Here's a JWT authentication implementation for your FastAPI app:\n\n"
                    "```python\n"
                    "from datetime import datetime, timedelta\n"
                    "from fastapi import Depends, HTTPException, status\n"
                    "from fastapi.security import OAuth2PasswordBearer\n"
                    "from jose import JWTError, jwt\n"
                    "from passlib.context import CryptContext\n\n"
                    "SECRET_KEY = os.environ['JWT_SECRET']\n"
                    "ALGORITHM = 'HS256'\n"
                    "ACCESS_TOKEN_EXPIRE = timedelta(minutes=30)\n"
                    "REFRESH_TOKEN_EXPIRE = timedelta(days=7)\n\n"
                    "pwd_context = CryptContext(schemes=['bcrypt'])\n"
                    "oauth2_scheme = OAuth2PasswordBearer(tokenUrl='token')\n"
                    "```\n\n"
                    "I'll add the token creation and validation functions. "
                    "Want me to include role-based access control as well?"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Yes, add role-based access control. I need three roles: "
                    "admin, editor, and viewer. Admins can do everything, "
                    "editors can create and update, viewers can only read. "
                    "Also add the token refresh endpoint."
                ),
            },
        ],
    },
    {
        "name": "typescript_react_form",
        "system": "ide",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Add form validation to this React component using react-hook-form and zod:\n\n"
                    "```tsx\n"
                    "export function SettingsForm({ user }: { user: User }) {\n"
                    "  const [saving, setSaving] = useState(false);\n\n"
                    "  const handleSubmit = async (e: React.FormEvent) => {\n"
                    "    e.preventDefault();\n"
                    "    setSaving(true);\n"
                    "    setSaving(false);\n"
                    "  };\n\n"
                    "  return (\n"
                    "    <form onSubmit={handleSubmit}>\n"
                    "      <input name=\"displayName\" defaultValue={user.displayName} />\n"
                    "      <input name=\"email\" type=\"email\" defaultValue={user.email} />\n"
                    "      <input name=\"website\" type=\"url\" />\n"
                    "      <textarea name=\"bio\" maxLength={500} />\n"
                    "      <button type=\"submit\" disabled={saving}>Save</button>\n"
                    "    </form>\n"
                    "  );\n"
                    "}\n"
                    "```\n\n"
                    "Validate: display name 2-50 chars, valid email, optional URL, bio max 500 chars. "
                    "Show inline error messages."
                ),
            },
        ],
    },
    {
        "name": "python_caching_decorator",
        "system": "cli",
        "turns": [
            {
                "role": "user",
                "content": (
                    "Write a TTL-based caching decorator that supports:\n"
                    "- Configurable TTL per decorated function\n"
                    "- Cache key based on function arguments\n"
                    "- Thread safety\n"
                    "- Max cache size with LRU eviction\n"
                    "- Optional cache bypass via a keyword argument\n"
                    "- Cache statistics (hits, misses, evictions)\n\n"
                    "Usage should look like:\n\n"
                    "```python\n"
                    "@cached(ttl=300, max_size=1000)\n"
                    "def get_user(user_id: int) -> User:\n"
                    "    return db.query(User).get(user_id)\n\n"
                    "user = get_user(42, _bypass_cache=True)\n"
                    "print(get_user.cache_stats())\n"
                    "```"
                ),
            },
        ],
    },
    {
        "name": "debug_memory_leak",
        "system": "ide",
        "turns": [
            {
                "role": "user",
                "content": (
                    "This WebSocket handler is leaking memory. After a few hours of running, "
                    "the process uses several GB of RAM. Find and fix the leaks:\n\n"
                    "```python\n"
                    "import asyncio\n"
                    "import json\n"
                    "from collections import defaultdict\n\n"
                    "connections = {}\n"
                    "message_history = defaultdict(list)\n"
                    "pending_tasks = []\n\n"
                    "async def handle_ws(websocket, path):\n"
                    "    client_id = id(websocket)\n"
                    "    connections[client_id] = websocket\n"
                    "    try:\n"
                    "        async for message in websocket:\n"
                    "            data = json.loads(message)\n"
                    "            message_history[client_id].append(data)\n"
                    "            task = asyncio.create_task(\n"
                    "                broadcast(data, exclude=client_id)\n"
                    "            )\n"
                    "            pending_tasks.append(task)\n"
                    "    except Exception:\n"
                    "        pass\n\n"
                    "async def broadcast(data, exclude=None):\n"
                    "    msg = json.dumps(data)\n"
                    "    for cid, ws in connections.items():\n"
                    "        if cid != exclude:\n"
                    "            await ws.send(msg)\n"
                    "```\n\n"
                    "Explain each leak and provide the fixed version."
                ),
            },
        ],
    },
]


def pick_scenario() -> Scenario:
    """Select a random coding scenario with a random client profile."""
    raw = random.choice(_RAW_SCENARIOS)
    client_key = random.choice(list(_CLIENTS))
    sys_key = raw.get("system", "ide")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPTS[sys_key]},
    ]
    messages.extend(raw["turns"])

    return Scenario(
        name=raw["name"],
        client=client_key,
        messages=tuple(messages),
        extra_headers=dict(_CLIENTS[client_key]),
    )
