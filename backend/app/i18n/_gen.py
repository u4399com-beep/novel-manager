
import json, os
base = os.path.dirname(os.path.abspath(__file__))
langs = {
    "ja": {"lang":"日本語","site_name":"鉛筆小説","home":"ホーム","search":"検索","search_placeholder":"小説・著者を検索","all_novels":"全小説","categories":"カテゴリ","start_reading":"読む","latest_update":"最新更新","hot_ranking":"人気","friend_links":"おすすめ","random_recommend":"おすすめ","no_description":"概要なし"},
}
for code, data in langs.items():
    path = os.path.join(base, f'{code}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  {code}: {data["lang"]}')
print('done')
