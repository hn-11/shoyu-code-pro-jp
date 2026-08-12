---
name: 上流アップデート
about: 上流フォントの新リリースに追従する（check-upstream.yml が自動起票）
title: "Upstream <repo> released <tag>"
labels: upstream
---

## 対象

- リポジトリ:
- 現在ピン留め中のタグ:
- 新しいタグ:

## 作業

- [ ] `.github/workflows/ci.yml` / `release.yml` の `env` とダウンロード
      URL のタグを更新
- [ ] ローカルまたは CI でビルドし `scripts/verify.py` が通ることを確認
- [ ] 見た目に影響する変更があれば README（`=`バー実測値など）を見直す
- [ ] 新しいタグでリリースを切る

## 補足

<!-- 上流の changelog へのリンクなど -->
