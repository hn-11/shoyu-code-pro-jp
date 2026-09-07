# Changelog

## v3.3.0

- 単独の ASCII 記号は32字全部（`!"#$%&'()*+,-./:;<=>?@[\]^_`{|}~`）を
  Monaspace に統一（以前は `=` `<` `>` `|` `~` の5字のみ）。合字自体が
  Monaspace 製のため、記号の骨格が単独字と合字とで食い違うと隣接時に
  継ぎ目が見えていた（`#` と `#[`、`-` と `->` など）。多くは Monaspace の
  cap 高・x-height が高いぶんの縦サイズ差（16〜150u、セル内に収まり
  ターミナルサイズでは2ピクセル未満）。`-` は `=` より124u短いが
  Monaspace 自身の字形どおり。SCP の cv14/cv15/cv16 を有効にすると
  `-` `*` `$` は SCP の字形に戻る
- 合字の calt/liga: 結合ルックアップの一致条件を、先頭1文字だけを見て
  残りをネストした LigatureSubst に委ねる形から、各合字の入力列を全部
  カバーするトリガールール（最長一致順）に変更。ネストしたルックアップが
  一致範囲を超えて何文字消費してよいかは OpenType の未定義動作で、
  HarfBuzz（kitty / WezTerm / Ghostty / VS Code のエディタ本体）は許容
  していたが DirectWrite（Windows Terminal）は v3.2.0 で `->` を素の文字
  のまま描画していた。Monaspace 本家の calt も入力を全部カバーする形。
  なお VS Code の統合ターミナル（xterm.js のリガチャアドオン、
  font-ligatures）は Fira Code 式の単純な置換ルールしか解釈せず、
  このフォントの合字はどのバージョンでも表示されない — これは今回の
  変更と無関係で従来通り
- 等幅メタデータ: `post.isFixedPitch=1`、PANOSE bProportion=9
  （HackGen / PlemolJP と同じ）、xAvgCharWidth を OS/2 v3+ の定義
  （0でない送り幅全部の平均）で再計算 — SHCJ の値の複写をやめた。
  Windows Terminal のフォント選択に「すべてのフォントを表示」なしで
  出るようになる
- OS/2 sxHeight / sCapHeight を各面の実際の `x` / `H` から実測。
  SHS の値（543/733）は Term/35（SCP 原寸で 488/655）に対して誤りだった
- ヒンティング: T2CharStringPen で描いた欧文・合字・（Term では）拡幅した
  全角グリフはこのフォント最初のバージョンから CFF ヒントを持っていな
  かった（SHCJ の欧文にはヒントがあった）。最終アウトラインで測った
  アライメントゾーン（BlueValues/OtherBlues/StdHW/StdVW）付きの CID
  FontDict を新設して割り当て、面を保存した後に AFDKO の otfautohint で
  ヒントを付ける（`requirements.txt` に afdko 追加、
  `SHOYU_SKIP_AUTOHINT=1` でローカルビルド時はスキップ可）。Source Han
  Sans 由来のグリフは元のヒントのまま。ヒント付与後、cffsubr（AFDKO の
  tx、`requirements.txt` に追加）で CFF をサブルーチン化: ビルドが生成
  する charstring はすべてフラットで、Term は全角グリフ約1.7万個を
  丸ごと再生成するため、ヒント付きだと Term の面が44%肥大（6.7MB）して
  いた。サブルーチン化後は4.6MB — ヒントを保ったまま v3.2.0（4.66MB）より
  小さい
- GDEF: SCP から移植した結合文字（U+0300〜036F、送り0）を class 3
  （Mark）に分類
- 来歴: nameID 0 にプロジェクトの著作権表示に加え Source Han Sans /
  Source Code Pro / Monaspace 各ドナーの表示をビルド時に取り込んで記載、
  nameID 9 にドナーのデザイナーを列挙、nameID 8 / 11 が Adobe ではなく
  プロジェクト（hn-11、リポジトリ URL）を指すように変更、
  OS/2 achVendID を Adobe の `ADBO` から未登録の `SHYU` に、
  nameID 3（unique ID）を `version;SHYU;PostScriptName` 形式に。
  Source Han Sans の古い DSIG は削除
- STAT テーブルを追加。各面は自分自身の wght / ital 値を1つずつだけ
  持つ（Regular は elidable で Bold にリンク、upright は elidable で
  Italic にリンク） — ファミリー全体の値を全面に列挙する形は Windows の
  ファミリーモデルを混乱させる（fontbakery: STAT_in_statics）ため
  避けた。OS/2 に WWS ビットを立て（version 4 に更新）、usWeightClass も
  ウェイトごとに明示的に設定

## v3.2.0

- 合字に文脈ガードを追加（Monaspace 本家の calt と同じ考え方）。演算子の並びが
  どの合字よりも長いときは合字化しない: `<|>` `&&=` `~~>` `->>` `==>` は
  素の文字のまま、`->` `-->` `<-->` `>>=` `===` は従来どおり合字。

## v3.1.0

- Light ウェイト復活（Monaspace 下限を超える分をアウトライン削りで合わせる）
- リリース版数を name ID 5 / fontRevision に刻印
- SCP の未収録約 600 字（`ł` `ğ` `ş` `ı` `ř` `₽` …）を半角で取り込み
- `−` `ς` `⁴` などのグリッド外グリフ修正
- 35/Term で半角カナを 1 セルに中央配置
- Term/35: `pwid`/`palt` を外し `hwid` 先のグリフをセルに合わせる
- NF 変種のアイコンを JP/35 でも 1 セル幅に
- 結合文字（U+0300〜036F）を送り 0 で取り込み、直前の文字に重なるように
- OS/2 の Unicode / コードページ範囲ビットを最終的な収録文字から再計算
- `makeotc.py` がファミリー内で cmap が一致しない面を検出して止まるように
- リリース zip に LICENSE 同梱

## v3.0.0

破壊的変更を含みます。

- ExtraLight/Light 削除（Light は 3.1.0 で復活）
- `= < > | ~` を Monaspace に
- Term の曖昧幅を HackGen Console 方式に変更

**既存ユーザーへの影響**: Term で `①` `※` が 2 セル幅になり、曖昧幅を
半角扱いするターミナルでは右隣に食み出す。Windows Terminal は
`"compatibility.ambiguousWidth": "wide"` で 2 セル確保できる。`←` `→` `≠`
`≤` `…` は 1 セル（Monaspace 版）。

- liga 単独で合字が出なかったバグ修正
- Term が CI で検証されるように
