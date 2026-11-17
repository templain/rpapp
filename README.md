# RP App

Djangoテンプレートで表示する、OIDCログイン対応のTodoアプリです。Todoはユーザー単位で分離され、管理者向けユーザー一覧・登録はGluu ServerのSCIM APIを利用します。

## セットアップ

Python 3.12以上を用意し、プロジェクトルートで次を実行します。

```sh
uv sync
cp .env.sample .env
# .env を編集して Gluu のOIDC/SCIM設定と秘密鍵を入力
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

`.venv`を直接使う場合は、`python -m venv .venv`、`.venv/bin/pip install -r requirements.txt`、`.env.sample`を`.env`にコピーして設定、`.venv/bin/python manage.py ...` の順に実行できます。既にプロセス環境に設定されている値は`.env`の値より優先されます。

`createsuperuser`で登録したアカウントは`/django-admin/`で使えます。Gluu OIDCでログインするアカウントに管理画面アクセス権を付与するには、Djangoシェルで該当ユーザーに`is_staff=True`を設定してください。管理者用画面は`/manage/users/`です。

## 環境変数

アプリはプロジェクトルートの`.env`を読み込みます。`.env.sample`をコピーし、OIDCのURLはGluu Server 4.4.0環境ごとのOIDC設定またはディスカバリー情報に記載された値に置き換えてください。推測した固定URLは使いません。

| 変数 | 用途 |
| --- | --- |
| `DJANGO_SECRET_KEY` | Djangoセッション署名鍵。本番環境では必ずランダムな秘密値を設定 |
| `DJANGO_DEBUG` | `true`でデバッグ有効（既定値`false`） |
| `DJANGO_ALLOWED_HOSTS` | 許可ホストのカンマ区切り。既定値`localhost,127.0.0.1,falcon` |
| `GLUU_OIDC_CLIENT_ID` / `GLUU_OIDC_CLIENT_SECRET` | Gluuで発行したOIDCクライアント資格情報 |
| `GLUU_OIDC_ISSUER` | OIDC issuer |
| `GLUU_OIDC_AUTHORIZATION_ENDPOINT` | 認可エンドポイント |
| `GLUU_OIDC_TOKEN_ENDPOINT` | トークンエンドポイント |
| `GLUU_OIDC_USERINFO_ENDPOINT` | UserInfoエンドポイント |
| `GLUU_OIDC_JWKS_ENDPOINT` | 署名検証用JWKSエンドポイント |
| `GLUU_OIDC_SIGN_ALGO` | IDトークン署名アルゴリズム（既定値`RS256`） |
| `GLUU_SCIM_BASE_URL` | Gluu SCIM APIのベースURL（`/Users`を含めない） |
| `GLUU_SCIM_BEARER_TOKEN` | SCIM API用Bearerトークン |
| `GLUU_SCIM_TIMEOUT_SECONDS` | SCIM HTTPタイムアウト秒数（既定値`10`） |
| `SQLITE_PATH` | SQLiteファイルパス（既定値`db.sqlite3`） |

OIDCのクライアントID/シークレットと各エンドポイント、SCIMのURL/トークンを`.env`に設定してからアプリを利用してください。TLS証明書検証は有効のままです。`.env`はGit管理対象外です。秘密値を`.env.sample`やソースコードに記載せず、サンプルの値を実際の設定・秘密情報に置き換えてください。

## 画面と認可

- `/todos/`、`/todos/new/`、`/todos/<id>/edit/`、`/todos/<id>/delete/`でTodoを管理します。
- 未認証リクエストはGluu OIDCログインへ進みます。OIDCの開始・コールバック・ログアウトURLのみ認証ミドルウェアの対象外です。
- Todoの検索・更新・削除は常にログインユーザーの所有物に限定されます。削除はCSRF保護されたPOSTのみ受け付けます。
- `/manage/users/`と`/manage/users/new/`は`is_staff`ユーザーのみアクセス可能です。ユーザー一覧取得と作成はGluu SCIM `GET /Users`、`POST /Users`を呼び出し、ローカルSQLiteにはユーザーを登録しません。

このアプリは画面をDjangoサーバーでレンダリングします。ブラウザー側のJavaScriptやSPAフレームワークは使用しません。
