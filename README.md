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
uv run python manage.py runsslserver 127.0.0.1:8000
```

`.venv`を直接使う場合は、`python -m venv .venv`、`.venv/bin/pip install -r requirements.txt`、`.env.sample`を`.env`にコピーして設定、`.venv/bin/python manage.py ...` の順に実行できます。既にプロセス環境に設定されている値は`.env`の値より優先されます。

起動後は `https://127.0.0.1:8000/` にアクセスします。`django-sslserver`の既定証明書は開発用の自己署名証明書です。ブラウザーに証明書警告が表示されるため、ローカル開発用途に限って使用してください。本番環境では、信頼された証明書を設定したリバースプロキシ等でTLSを終端してください。独自の証明書と秘密鍵を指定する場合は、`uv run python manage.py help runsslserver`でオプションを確認して指定します。

この開発URLをGluuのクライアント設定から利用する場合、Login Redirect URIには `https://127.0.0.1:8000/oidc/callback/` を登録してください。ホスト名やポートを変えた場合は、実際にブラウザーからアクセスするHTTPS URLに合わせて変更します。
Gluuからログアウト後に戻るURI `https://127.0.0.1:8000/` も、クライアントのPost Logout Redirect URIsに登録してください。

`createsuperuser`で登録したアカウントは`/django-admin/`で使えます。Gluu OIDCログインでは、IDトークンまたはUserInfoの`user_permission` claimが文字列`admin`または`admin`を含む文字列配列の場合に、そのDjangoユーザーを`is_staff=True`に同期します。claimがない、または文字列／文字列配列以外の場合は認証処理がエラーになります。管理者用画面は`/manage/users/`です。権限変更は次回OIDCログイン時に反映されます。

## 環境変数

アプリはプロジェクトルートの`.env`を読み込みます。`.env.sample`をコピーし、OIDCのURLはGluu Server 4.4.0環境ごとのOIDC設定またはディスカバリー情報に記載された値に置き換えてください。推測した固定URLは使いません。

OIDCログイン要求では`openid email profile view_profile`のscopeを要求します。Gluuクライアントで`view_profile`を許可し、そのscopeのClaimsにoxAuth claim nameが`user_permission`のclaimを含めてください。claimはIDトークンまたはUserInfoのいずれかで返される必要があります。

OIDCの認証コードフローではPKCEを常に使用します。認可リクエストにはランダムなcode verifierから生成した`code_challenge`と`code_challenge_method=S256`を含め、トークンリクエストではセッションに保存したcode verifierを送信します。これにより認証コードの横取りリスクを低減します。PKCEはブラウザーを介するOIDC認証に適用され、サーバー間のSCIM OAuth 2.0 `client_credentials`フローには適用しません。

Todo一覧のユーザー表示名は、Gluu UserInfoの`given_name`と`family_name`を優先して使用します。これらがない場合は`name`を使用し、名前claimがない場合に限り匿名化されたDjango usernameを表示します。Gluuクライアントから標準OIDCのプロフィールclaimを返すよう設定してください。


ユーザー登録画面で指定した初期パスワードは、SCIM `POST /Users`のトップレベル`password`属性としてGluuへ送信されます。権限はGluuのUser拡張スキーマ内の多値属性`role`に`["user"]`として設定します。OIDCのclaim名`user_permission`とSCIM属性名`role`は別の名前です。これらの値はアプリ側には保存しません。パスワードを送信するため、`GLUU_SCIM_VERIFY_SSL=true`にして、Gluuの証明書を発行した信頼できるCAをアプリ環境に設定してください。TLS証明書検証を無効にしたままでは、通信を傍受されパスワードが漏れるおそれがあります。

| 変数 | 用途 |
| --- | --- |
| `DJANGO_SECRET_KEY` | Djangoセッション署名鍵。本番環境では必ずランダムな秘密値を設定 |
| `DJANGO_DEBUG` | `true`でデバッグ有効（既定値`false`） |
| `DJANGO_ALLOWED_HOSTS` | Djangoが受け付けるHostヘッダーのカンマ区切り（Webサーバーのバインド先とは別）。既定値`localhost,127.0.0.1,falcon` |
| `GLUU_OIDC_CLIENT_ID` / `GLUU_OIDC_CLIENT_SECRET` | Gluuで発行したOIDCクライアント資格情報 |
| `GLUU_OIDC_ISSUER` | OIDC issuer |
| `GLUU_OIDC_AUTHORIZATION_ENDPOINT` | 認可エンドポイント |
| `GLUU_OIDC_TOKEN_ENDPOINT` | トークンエンドポイント |
| `GLUU_OIDC_USERINFO_ENDPOINT` | UserInfoエンドポイント |
| `GLUU_OIDC_JWKS_ENDPOINT` | 署名検証用JWKSエンドポイント |
| `GLUU_OIDC_END_SESSION_ENDPOINT` | OIDCディスカバリー情報の`end_session_endpoint` |
| `GLUU_OIDC_SIGN_ALGO` | IDトークン署名アルゴリズム（既定値`RS256`） |
| `GLUU_OIDC_PKCE_CODE_CHALLENGE_METHOD` | PKCEのchallenge method（既定値`S256`。認可サーバーがS256をサポートすることが必要） |
| `GLUU_OIDC_PKCE_CODE_VERIFIER_SIZE` | PKCEのcode verifier文字数（RFC 7636準拠の43～128、既定値`64`） |
| `GLUU_SCIM_BASE_URL` | Gluu SCIM APIのベースURL（`/Users`を含めない） |
| `GLUU_SCIM_CLIENT_ID` / `GLUU_SCIM_CLIENT_SECRET` | SCIM用にGluuで登録したOAuthクライアントID（通常はoxTrustのクライアントID/inum）とsecret。`client_credentials` grantを許可 |
| `GLUU_SCIM_SCOPE` | SCIM OAuth scope。既定値は`https://gluu.org/scim/users.read https://gluu.org/scim/users.write` |
| `GLUU_SCIM_TOKEN_AUTH_METHOD` | Token Endpoint認証方式。`client_secret_basic`（既定）または`client_secret_post` |
| `GLUU_SCIM_TIMEOUT_SECONDS` | SCIM HTTPタイムアウト秒数（既定値`10`） |
| `GLUU_SCIM_VERIFY_SSL` | SCIMのTLS証明書を検証するか（`false`で無効。既定値`false`） |
| `SQLITE_PATH` | SQLiteファイルパス（既定値`db.sqlite3`） |

OIDCのクライアントID/シークレットと各エンドポイント、SCIMのURL/トークンを`.env`に設定してからアプリを利用してください。SCIMのTLS証明書検証は既定で無効です。これは自己署名証明書を使う開発環境向けであり、通信を傍受・偽装される危険があるため、本番環境では`GLUU_SCIM_VERIFY_SSL=true`にして信頼されたCA証明書を設定してください。`.env`はGit管理対象外です。秘密値を`.env.sample`やソースコードに記載せず、サンプルの値を実際の設定・秘密情報に置き換えてください。

## 画面と認可

- `/todos/`、`/todos/new/`、`/todos/<id>/edit/`、`/todos/<id>/delete/`でTodoを管理します。
- 未認証リクエストはGluu OIDCログインへ進みます。OIDCの開始・コールバック・ログアウトURLのみ認証ミドルウェアの対象外です。
- Todoの検索・更新・削除は常にログインユーザーの所有物に限定されます。削除はCSRF保護されたPOSTのみ受け付けます。
- `/manage/users/`と`/manage/users/new/`は`is_staff`ユーザーのみアクセス可能です。ユーザー一覧取得と作成はGluu SCIM `GET /Users`、`POST /Users`を呼び出し、ローカルSQLiteにはユーザーを登録しません。

このアプリは画面をDjangoサーバーでレンダリングします。ブラウザー側のJavaScriptやSPAフレームワークは使用しません。

## ログイン画面のGluu Serverへの反映
```
sudo curl -fsSL "https://raw.githubusercontent.com/templain/rpapp/master/gluu/custom_login.xhtml"   -o /opt/gluu-server/opt/gluu/jetty/oxauth/custom/pages/auth/custom_login.xhtml
```
