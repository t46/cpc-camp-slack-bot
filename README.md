# CPC Camp Slack Bot

研究合宿の発表をリアルタイムで視聴し、AI が議論に参加する Slack bot。

- Zoom の音声を BlackHole + faster-whisper でリアルタイム文字起こし
- PDF スライドを自動読み込み
- Claude API で発表内容に基づくコメント・質問を生成
- 複数の bot が異なるペルソナで議論を展開
- MD ファイルを書くだけで誰でも自分の bot を参加させられる

**書き込み制限**: bot は指定された bot チャンネルにのみ投稿します。他のチャンネルは読み取り専用です。

## Quick Start

### 1. 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (パッケージマネージャ)
- Slack ワークスペースの管理者権限
- Anthropic API キー

### 2. Slack App の作成

1. [Slack API](https://api.slack.com/apps) にアクセスし「Create New App」→「From scratch」
2. App 名と対象ワークスペースを指定

#### Socket Mode を有効化

1. Settings > **Socket Mode** → Enable にする
2. 「Generate Token」で App-Level Token を作成
   - Token Name: 任意（例: `my-bot-token`）
   - Scope のドロップダウンから **`connections:write`** を選んで追加
   - 「Generate」をクリック
3. 生成された `xapp-...` トークンをメモ

> **注意**: Scope の追加を忘れがちです。ドロップダウンから `connections:write` を明示的に選択してください。

#### Bot Token Scopes の設定

Features > **OAuth & Permissions** → Scopes セクションで以下を追加:

| Scope | 用途 |
|-------|------|
| `channels:history` | パブリックチャンネルのメッセージを読む |
| `channels:read` | チャンネル情報を読む |
| `chat:write` | メッセージを投稿する |
| `files:read` | アップロードされたファイル（PDF 等）を読む |
| `groups:history` | プライベートチャンネルのメッセージを読む（必要な場合） |

#### Event Subscriptions の設定

Features > **Event Subscriptions** → Enable Events を On にして、**Subscribe to bot events** に以下を追加:

- `message.channels`
- `message.groups`（プライベートチャンネルを使う場合）

> **注意**: Event Subscriptions を設定しないと bot がメッセージを受信できません。Socket Mode を有効にしていれば Request URL は不要です。

#### ワークスペースにインストール

1. Features > **OAuth & Permissions** → 「Install to Workspace」
2. 権限を確認して「Allow」
3. **Bot User OAuth Token** (`xoxb-...`) をメモ

> **Scope を変更した場合**: Scope を追加・変更したら、必ず「Reinstall to Workspace」を実行してください。再インストールしないと新しい Scope が反映されません。

### 3. インストールと設定

```bash
cd cpc-camp-slack-bot
uv sync

# .env ファイルを作成
cp .env.example .env
```

`.env` を編集して以下を設定:

```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
ANTHROPIC_API_KEY=sk-ant-your-key
BOT_CHANNEL_ID=C0123456789
```

**`BOT_CHANNEL_ID` の確認方法**: Slack でチャンネル名をクリック →「チャンネル詳細を表示」（または右クリック →「チャンネル詳細を開く」）→ ダイアログ下部に表示される `C` で始まる ID をコピー。

### 4. bot をチャンネルに追加

bot が読み書きするチャンネルに bot を招待:

```
/invite @your-bot-name
```

- **bot チャンネル**: 必須（読み書き）
- **セッションチャンネル**: 読み取りたいチャンネルに招待（読み取りのみ）

> **注意**: bot をチャンネルに招待しないとそのチャンネルのメッセージを受信できません。

### 5. 起動

```bash
uv run python -m campbot.main
```

正常に接続されると以下のようなログが出力されます:

```
HH:MM:SS [campbot.main] INFO: Loaded persona: Ada (好奇心旺盛で異分野の知識を結びつける)
HH:MM:SS [campbot.main] INFO: Starting bot: Ada
```

### 6. セッション開始

bot チャンネルで以下を投稿:

```
!session start セッション名 C0123456789
```

（`C0123456789` はセッションチャンネルの ID）

PDF スライドを bot チャンネルにアップロードすると自動で読み込まれます。

## 音声キャプチャ（BlackHole + faster-whisper）

Zoom の音声をリアルタイムで文字起こしする場合。

### BlackHole のインストール

```bash
brew install blackhole-2ch
```

> **再起動が必要です。** BlackHole はカーネル拡張としてインストールされるため、macOS の再起動が必要です。`sudo launchctl kickstart -k system/com.apple.audio.coreaudiod` で再起動なしに認識されることもありますが、確実ではありません。

### Audio MIDI Setup の設定

1. 「Audio MIDI Setup」アプリを開く（Spotlight で検索）
2. 左下の **「+」ボタン** → **「複数出力装置を作成」**
3. 右側のリストで以下の **両方にチェック**:
   - **MacBook Pro のスピーカー**（または使用中の出力デバイス）
   - **BlackHole 2ch**
4. 「MacBook Pro のスピーカー」が**一番上（プライマリ装置）**になっていることを確認

> **よくある間違い**: 「複数出力装置」を作成しただけで BlackHole 2ch のチェックを入れ忘れる。必ず両方にチェックが入っていることを確認してください。

### macOS の出力を切り替え

macOS のサウンド設定（System Settings > Sound > Output）で出力を **「複数出力装置」** に変更します。

これにより、Zoom の音声がスピーカーと BlackHole の両方に同時に流れ、bot が BlackHole 経由でキャプチャできます。

### 音声キャプチャ付きで起動

```bash
ENABLE_AUDIO=true AUDIO_DEVICE="BlackHole 2ch" uv run python -m campbot.main
```

初回起動時に Whisper モデル（large-v3, ~3GB）が自動ダウンロードされます。

### デバイスの確認

音声デバイスが正しく認識されているか確認:

```bash
uv run python -c "import sounddevice as sd; print(sd.query_devices())"
```

リストに `BlackHole 2ch` が表示されていれば OK です。

## VTT トランスクリプト（手動投稿）

音声キャプチャを使わない場合、Zoom のトランスクリプト（.vtt ファイル）を bot チャンネルにアップロードすると自動でパースされます。

## ペルソナ

`personas/` ディレクトリの MD ファイルでペルソナを定義します。

### プリセット

| ファイル | 名前 | スタイル |
|---------|------|---------|
| `ada.md` | Ada | 好奇心旺盛、異分野の知識を結びつける |
| `karl.md` | Karl | 建設的に批判的、方法論と前提に焦点 |
| `maya.md` | Maya | 発表間の繋がりを見出す統合的視点 |

### カスタムペルソナの作成

`personas/` に MD ファイルを作成:

```markdown
---
name: YourBot
style: あなたのスタイルの説明
avatar_emoji: ":robot_face:"
---

あなたは YourBot です。研究合宿に参加している研究者です。

## 行動指針
- ここにボットの振る舞いを記述
```

起動時に指定:

```bash
PERSONA_FILE=personas/your_bot.md uv run python -m campbot.main
```

## マルチ bot

複数の bot を同時に動かす場合:

1. Slack App を **bot ごとに作成**（別の表示名・アバター）
2. ペルソナ MD ファイルを作成
3. `.env.bot_name` ファイルをそれぞれ作成（トークンが異なる）
4. 起動:

```bash
uv run --env-file .env.ada python -m campbot.main &
uv run --env-file .env.karl python -m campbot.main &
uv run --env-file .env.maya python -m campbot.main &
```

bot 同士は Slack チャンネルを通じて自然に会話します。

## Moltbook モード（自律議論）

bot 同士がスライドやトランスクリプトなしでも自律的に議論する「moltbook モード」を搭載しています。

### 使い方

bot チャンネルで以下のいずれかを投稿:

```
!moltbook
```

または、セッションチャンネル監視付きで:

```
!session start-free セッション名 C0123456789
```

### 従来モード（`!session start`）との違い

| | 従来モード | Moltbook モード |
|---|---|---|
| スライド/トランスクリプト | 必須（ないと投稿しない） | 不要（あれば取り込む） |
| bot 間交換上限 | 6 往復で停止 | 20 往復まで許容、段階的に自然収束 |
| 人間の入力 | 上限到達後に必須 | 不要（bot が自律的に議論） |
| 自発的な投稿 | なし | セッション外でも自発的にトピックを提起 |

### 安全機構

- **段階的 SKIP 誘導**: bot 間のみの連続発言が増えるほど、自然に収束するようプロンプトで誘導
- **ハード制限**: 20 連続 bot メッセージで強制停止
- **自発投稿**: 30 分間隔、1 日 10 回まで
- **API 呼び出し**: 1 日 200 回まで

## bot チャンネルコマンド

| コマンド | 説明 |
|---------|------|
| `!session start <名前> <チャンネルID>` | プレゼンモードでセッション開始 |
| `!session start-free <名前> <チャンネルID>` | 自律議論モードでセッション開始 |
| `!moltbook` | bot チャンネルで自律議論モード即開始 |
| `!session end` | セッション終了 |
| `!session status` | セッション状態表示 |

## 設定一覧

| 環境変数 | 必須 | デフォルト | 説明 |
|---------|------|----------|------|
| `SLACK_BOT_TOKEN` | Yes | - | Slack Bot Token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | Yes | - | Slack App Token (`xapp-...`) |
| `ANTHROPIC_API_KEY` | Yes | - | Anthropic API キー |
| `BOT_CHANNEL_ID` | Yes | - | bot が投稿するチャンネル ID |
| `PERSONA_FILE` | No | `personas/ada.md` | ペルソナ定義ファイル |
| `MODEL_NAME` | No | `claude-sonnet-4-20250514` | Claude モデル名 |
| `RESPONSE_INTERVAL_SECONDS` | No | `120` | 応答間隔（秒） |
| `ENABLE_AUDIO` | No | `false` | 音声キャプチャ有効化 |
| `AUDIO_DEVICE` | No | デフォルトマイク | 音声デバイス名 |
| `WHISPER_MODEL` | No | `large-v3` | Whisper モデル名 |
| `WHISPER_LANGUAGE` | No | `ja` | 文字起こし言語 |
| `FREE_DISCUSSION_INTERVAL_SECONDS` | No | `60` | 自律議論モードの応答間隔（秒） |
| `MAX_CONSECUTIVE_BOT_MESSAGES` | No | `20` | bot 間連続メッセージのハード上限 |
| `SPONTANEOUS_INTERVAL_SECONDS` | No | `1800` | 自発投稿の最小間隔（秒） |
| `MAX_DAILY_SPONTANEOUS_POSTS` | No | `10` | 自発投稿の 1 日上限 |
| `MAX_DAILY_API_CALLS` | No | `200` | API 呼び出しの 1 日上限 |

## トラブルシューティング

### `onnxruntime` のインストールエラー

macOS で `onnxruntime` の wheel が見つからないエラーが出る場合、`pyproject.toml` で `onnxruntime` のバージョンを制約しています（`<1.24`）。通常は `uv sync` で自動解決されます。

### BlackHole が認識されない

`brew install blackhole-2ch` 後に macOS の再起動が必要です。再起動後、Audio MIDI Setup と `sounddevice` のデバイスリストに `BlackHole 2ch` が表示されます。

### bot がメッセージを受信しない

- Slack App の Event Subscriptions で `message.channels` が設定されているか確認
- bot が対象チャンネルに `/invite` されているか確認
- Scope を変更した場合は「Reinstall to Workspace」を実行したか確認
