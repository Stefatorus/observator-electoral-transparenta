from GoogleAds.main import GoogleAds, show_regions_list

a = GoogleAds()
keyword = "Google LLC"
creatives = a.get_creative_Ids(keyword, 200)  # Get 200 creatives if available
if creatives["Ad Count"]:
    advertisor_id = creatives["Advertisor Id"]
    for creative_id in creatives["Creative_Ids"]:
        # print(a.get_breif_ads(advertisor_id, creative_id))
        print(a.get_detailed_ad(advertisor_id, creative_id))
else:
    print("Got nothing")