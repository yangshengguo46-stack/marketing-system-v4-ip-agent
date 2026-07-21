# Douyin official metric collection

The IP Agent distribution contains a first-party adapter for Douyin's official
`POST https://open.douyin.com/api/apps/v1/video/query/` endpoint. It queries
current statistics for public videos owned by the authorized user and writes
the result as a post-level `snapshot` linked to the existing publish receipt.

This is not scraping. The official capability requires an enterprise developer
application, the `ma.video.bind` scope, approval for video-data query access and
user authorization. Only videos belonging to the access token's user can be
queried. Private or unreturned videos are stored as `unavailable`, never as
zero performance. Follow the current official documentation:

- <https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/server/basic-abilities/video-id-convert/user-video-data/video-data>
- <https://developer.open-douyin.com/capacity-center-page/capacity-detail/7448483112163590181>

## Normalization

| Douyin field | Personal-IP metric |
|---|---|
| `play_count` | `views` |
| `digg_count` | `likes` |
| `comment_count` | `comments` |
| `share_count` | `shares` |
| `download_count` | `downloads` |
| `forward_count` | `forwards` |

Views, likes, comments and shares determine whether the result is complete.
Optional download/forward counters are retained when returned. Provider log id,
scope, review/video status and missing fields stay in coverage metadata. The
collector classifies expired credentials, missing permission, quota, transient
and network failures without logging or returning the access token.

## Credentialed smoke test

For developer verification only:

```bash
export DOUYIN_ACCESS_TOKEN='...'
export DOUYIN_OPEN_ID='...'
export DOUYIN_ITEM_ID='...'
make douyin-metrics-smoke
```

The command never prints those credentials. It is not the production
credential path, and the Gateway does not offer a public endpoint that accepts
raw Douyin tokens.

## Production mini-app authorization

Configure the approved enterprise mini-app on the Gateway:

```dotenv
DOUYIN_MINI_APP_ID=tt-your-mini-app-id
DOUYIN_MINI_APP_SECRET=your-mini-app-secret
PERSONAL_IP_CREDENTIAL_KEY=generate-a-random-secret-of-at-least-32-characters
```

The product flow follows the capability's mini-app contract, not website QR
OAuth:

1. Create a one-use session with
   `POST /api/personal-ip/platform-connections/douyin/authorization-sessions`
   and the target `account_id`.
2. In a real Douyin mini-app, call `tt.showDouyinOpenAuth` with the returned
   `scope_list`, and call `tt.login` for the mini-app login code.
3. Submit the returned permission `ticket`, login `code` and one-use `state` to
   the returned completion endpoint.
4. The Gateway exchanges both codes server-side, stores only a SHA-256 digest
   of the state, and encrypts access/refresh tokens at rest. List, refresh and
   disconnect operations return connection metadata only.

The code/ticket are one-use inputs. Access tokens, refresh tokens, the mini-app
secret and the `code2Session` session key are never returned from these APIs.
`DELETE /api/personal-ip/platform-connections/{id}` disconnects locally and
physically removes the encrypted token row; users can separately cancel the
app's upstream authorization in Douyin. Connections bind to operated account
records only—they never narrow a DeerFlow conversation to one account.

If `PERSONAL_IP_CREDENTIAL_KEY` is absent, the Gateway derives a
domain-separated key from its stable persisted auth JWT secret for local
first-run convenience. Production deployments should set the dedicated key
of at least 32 characters before the first authorization and keep it stable;
changing it makes existing
encrypted credentials unreadable and requires reauthorization.

The official capability is for data belonging to the authorizing user and must
not be repackaged as an external data service or unrestricted platform-wide
analytics product.
