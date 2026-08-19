"""intel_config.py — 情报系统配置"""

TWITTER_USERS = [
    "karpathy", "ylecun", "AndrewYNg", "fchollet", "jeremyphoward",
    "DrJimFan", "ilyasut", "_akhaliq", "drfeifei", "demishassabis",
    "dotey", "easychen",
]

NITTER_INSTANCES = [
    "https://nitter.net",
]

GITHUB_USERS = ["karpathy"]
GITHUB_REPOS = [
    "RVC-Boss/GPT-SoVITS", "SYSTRAN/faster-whisper",
    "kqwang/phase-recovery",
    "1c7/chinese-independent-developer", "loonggg/DevMoneySharing",
]

BILIBILI_UIDS = [20259914,22697887,37858284,285286947,286554413,28143041,491240131,259612040,508984798,11409145,441167301,130914376]
YOUTUBE_CHANNELS = []

ARXIV_CONFIG = {
    "wavefront_shaping": {
        "categories": ["physics.optics", "eess.IV"],
        "keywords": ["wavefront shaping", "scattering media", "complex media",
                      "transmission matrix", "scattering matrix", "speckle correlation",
                      "memory effect", "deep tissue imaging", "optical phase conjugation",
                      "guide star", "multimode fiber imaging", "adaptive optics"],
        "max_results": 12,
    },
    "computational_imaging": {
        "categories": ["eess.IV", "cs.CV", "physics.optics"],
        "keywords": ["computational imaging", "phase retrieval", "lensless imaging",
                      "Fourier ptychography", "holography", "wavefront sensing",
                      "coded aperture", "optical diffraction tomography", "structured illumination"],
        "max_results": 6,
    },
    "ai": {
        "categories": ["cs.AI", "cs.LG", "cs.CL", "cs.CV"],
        "keywords": ["large language model", "LLM", "diffusion model", "transformer",
                      "multimodal", "text-to-speech", "voice cloning", "vision language model"],
        "max_results": 2,
    },
}

PAPER_PRIORITY_AUTHORS = [
    "Sylvain Gigan", "Allard P. Mosk", "Ivo M. Vellekoop", "Ori Katz",
    "Wonshik Choi", "YongKeun Park", "Changhuei Yang", "Lihong Wang",
    "Meng Cui", "Chris Xu", "Hui Cao", "Stefan Rotter",
    "A. Douglas Stone", "Azriel Genack", "Xiaopeng Shao", "Xin Jin",
    "Jacopo Bertolotti", "Sebastien Popoff", "Tomas Cizmar",
    "David B. Phillips", "Robert Prevedel", "Na Ji",
    "Roarke Horstmeyer", "Ryoichi Horisaki", "Rafael Piestun",
]

PAPER_SECONDARY_AUTHORS = [
    "Laura Waller", "Gordon Wetzstein", "Aydogan Ozcan",
    "Ashok Veeraraghavan", "Gabriel Popescu", "Guoan Zheng", "Chao Zuo",
    "Lei Tian", "Qionghai Dai", "Florian Willomitzer",
]

PAPER_AI_AUTHORS = [
    "Yann LeCun", "Geoffrey Hinton", "Fei-Fei Li", "Ilya Sutskever",
]

ARXIV_AUTHORS = PAPER_PRIORITY_AUTHORS + PAPER_SECONDARY_AUTHORS + PAPER_AI_AUTHORS
ARXIV_MAX_RESULTS = 8
PAPER_LOOKBACK_HOURS = 24
ARXIV_SINCE_HOURS = PAPER_LOOKBACK_HOURS
ARXIV_ENABLE_AUTHORS = True
ARXIV_DAILY_AUTHOR_LIMIT = len(ARXIV_AUTHORS)
ARXIV_AUTHOR_MAX_RESULTS = 2

PAPER_ENABLE_SEMANTIC_SCHOLAR = True
PAPER_SEMANTIC_SCHOLAR_FALLBACK_ONLY = True
PAPER_SEMANTIC_SCHOLAR_AUTHOR_LIMIT = 6
PAPER_SEMANTIC_SCHOLAR_MAX_RESULTS = 10
PAPER_ENABLE_CROSSREF_DAILY_SCAN = True
PAPER_CROSSREF_MAX_PER_JOURNAL = 8

MONEY_TWITTER_USERS = []
MONEY_CONFIG = {
    "rss_feeds": [
        "https://hnrss.org/frontpage",
        "https://www.v2ex.com/feed/tab/creative.xml",
        "https://www.producthunt.com/feed",
    ],
    "keywords": [
        "赚钱", "副业", "信息差", "搬砖", "套利", "被动收入", "独立开发", "出海",
        "side project", "side hustle", "indie hacker", "passive income", "monetize",
        "MRR", "ARR", "making money", "bootstrap", "solopreneur", "micro-saas",
    ],
    "telegram_channels": [], "jike_topics": [],
}

BRIEFING_CONFIG = {
    "schedule_time": "08:00", "timezone": "Asia/Tokyo",
    "max_items_per_source": 5, "save_history": True, "history_dir": "intel_history",
}
