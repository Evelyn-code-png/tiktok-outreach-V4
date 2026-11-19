"""Separate EasyKOL content tags from inferred personal traits.

EasyKOL's aiTags mix content topics (skincare, tutorials) with traits its own AI
guessed from videos (gender, race, age, looks, family). Content fit should rest on
content, so personal traits are removed before any AI prompt and shown to the
user only as labeled, inferred information.
"""
import re

# tag (lowercase) -> (category, English label)
TRAITS = {
    # gender
    '女': ('gender', 'Female'), '男': ('gender', 'Male'), '女性': ('gender', 'Female'), '男性': ('gender', 'Male'),
    'female': ('gender', 'Female'), 'male': ('gender', 'Male'), 'woman': ('gender', 'Female'), 'man': ('gender', 'Male'),
    # race and ethnicity
    '白人': ('race', 'White'), '黑人': ('race', 'Black'), '亚裔': ('race', 'Asian'), '亚洲人': ('race', 'Asian'),
    '拉丁裔': ('race', 'Latino'), '西班牙裔': ('race', 'Hispanic'), '印度裔': ('race', 'South Asian'),
    '中东裔': ('race', 'Middle Eastern'), '混血': ('race', 'Mixed'),
    'white': ('race', 'White'), 'black': ('race', 'Black'), 'asian': ('race', 'Asian'),
    'latino': ('race', 'Latino'), 'latina': ('race', 'Latina'), 'hispanic': ('race', 'Hispanic'),
    # age
    '青年': ('age', 'Young adult'), '中年': ('age', 'Middle-aged'), '老年': ('age', 'Older adult'),
    '少年': ('age', 'Teen'), '青少年': ('age', 'Teen'), '儿童': ('age', 'Child'),
    'teen': ('age', 'Teen'), 'young': ('age', 'Young adult'),
    # appearance
    '高颜值': ('appearance', 'Rated attractive'), '颜值': ('appearance', 'Appearance rating'),
    '帅哥': ('appearance', 'Rated attractive'), '美女': ('appearance', 'Rated attractive'),
    '大码': ('appearance', 'Plus size'),
    # family and relationships
    '有娃': ('family', 'Has children'), '宝妈': ('family', 'Parent'), '宝爸': ('family', 'Parent'),
    '情侣': ('family', 'Couple'), '孕妇': ('family', 'Pregnant'), '已婚': ('family', 'Married'),
}

SPLIT = re.compile(r'\s*[,，;；|、/]\s*')


def split(text):
    """Return (content tags as text, list of inferred traits)."""
    content, traits, seen = [], [], set()
    for raw in SPLIT.split(str(text or '')):
        tag = raw.strip()
        if not tag:
            continue
        trait = TRAITS.get(tag.lower())
        if trait:
            if trait not in seen:
                seen.add(trait)
                traits.append({'category': trait[0], 'label': trait[1]})
        else:
            content.append(tag)
    return ', '.join(content), traits


def content_only(text):
    return split(text)[0]
