from pydantic import BaseModel, Json, Field
from uuid import UUID
from enum import Enum
class AiResponseOut(BaseModel):
    id_agent: UUID
    id_model:UUID
    id_ai_api_key: UUID
    response: Json
    
###################
### Graph Generation
###################
class GraphType(Enum):
    AREA = "AREA"
    TOPIC = "TOPIC"
    CONCEPT = "CONCEPT"
    SUBCONCEPT = "SUBCONCEPT"
    
class EdgeType(Enum):
    SUBTOPIC = "SUBTOPIC"
    PREREQUISITE = "PREREQUISITE"

class ManipulateGraphResponse(BaseModel):
    graph_title: str
  # graph_description:str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    
class GraphNode(BaseModel):
    node_id: int
    title: str
  # description:str
    type: GraphType
class GraphEdge(BaseModel):
    source_node: int
    target_node: int
    type: EdgeType
    
###################
### External resources query generation
###################
class SearchQueries(BaseModel):
    paper_query: str
    search_query: str
    yt_videos_query: str
    books_query: str

### YT
class YtSearchResult(BaseModel):
    kind: str
    etag: str
    id: YtId
    snippet: YtSnippet

class YtId(BaseModel):
    kind: str
    videoId: str
    
class YtSnippet(BaseModel):
     publishedAt: str 
     channelId: str
     title: str
     description: str
     thumbnails: YtThumbnails
     channelTitle: str
     liveBroadcastContent: str
     publishTime: str
         
class YtThumbnails(BaseModel):
    default: YtThumbnail
    medium:  YtThumbnail
    high: YtThumbnail
    
class YtThumbnail(BaseModel):
    url: str
    width:  int
    height: int

### Papers
class S2SearchResult(BaseModel):
    total: int
    offset: int
    next: int | None = None
    data: list["S2Paper"]

class S2Paper(BaseModel):
    paperId: str
    externalIds: "S2ExternalIds | None" = None
    corpusId: int | None = None
    publicationVenue: "S2PublicationVenue | None" = None
    url: str | None = None
    title: str
    venue: str | None = None
    year: int | None = None
    referenceCount: int
    citationCount: int
    influentialCitationCount: int
    isOpenAccess: bool
    openAccessPdf: "S2OpenAccessPdf | None" = None
    fieldsOfStudy: list[str] | None = None
    s2FieldsOfStudy: list["S2FieldOfStudy"] = []
    publicationTypes: list[str] | None = None
    publicationDate: str | None = None
    journal: "S2Journal | None" = None
    citationStyles: "S2CitationStyles | None" = None
    authors: list["S2Author"]
    abstract: str | None = None

class S2ExternalIds(BaseModel):
    DOI: str | None = None
    CorpusId: int | None = None
    ArXiv: str | None = None
    PubMed: str | None = None
    DBLP: str | None = None

class S2PublicationVenue(BaseModel):
    id: str | None = None
    name: str
    type: str | None = None
    alternate_names: list[str] | None = None
    url: str | None = None

class S2OpenAccessPdf(BaseModel):
    url: str | None = None
    status: str | None = None
    license: str | None = None
    disclaimer: str | None = None

class S2FieldOfStudy(BaseModel):
    category: str
    source: str

class S2Journal(BaseModel):
    name: str
    volume: str | None = None
    pages: str | None = None

class S2CitationStyles(BaseModel):
    bibtex: str | None = None

class S2Author(BaseModel):
    authorId: str | None = None
    name: str

### Books    
class GbBook(BaseModel):
    kind: str
    id: str
    etag: str
    selfLink: str
    volumeInfo: "GbVolumeInfo"
    saleInfo: "GbSaleInfo"
    accessInfo: "GbAccessInfo"
    searchInfo: "GbSearchInfo | None" = None


class GbVolumeInfo(BaseModel):
    title: str
    subtitle: str | None = None
    authors: list[str] | None = None
    publisher: str | None = None
    publishedDate: str | None = None
    description: str | None = None
    industryIdentifiers: list["GbIndustryIdentifier"] | None = None
    readingModes: "GbReadingModes | None" = None
    pageCount: int | None = None
    printType: str | None = None
    categories: list[str] | None = None
    averageRating: float | None = None
    ratingsCount: int | None = None
    maturityRating: str | None = None
    allowAnonLogging: bool | None = None
    contentVersion: str | None = None
    panelizationSummary: "GbPanelizationSummary | None" = None
    imageLinks: "GbImageLinks | None" = None
    language: str | None = None
    previewLink: str | None = None
    infoLink: str | None = None
    canonicalVolumeLink: str | None = None


class GbIndustryIdentifier(BaseModel):
    type: str
    identifier: str


class GbReadingModes(BaseModel):
    text: bool
    image: bool


class GbPanelizationSummary(BaseModel):
    containsEpubBubbles: bool
    containsImageBubbles: bool


class GbImageLinks(BaseModel):
    smallThumbnail: str
    thumbnail: str


class GbSaleInfo(BaseModel):
    country: str
    saleability: str
    isEbook: bool
    listPrice: "GbPrice | None" = None
    retailPrice: "GbPrice | None" = None
    buyLink: str | None = None
    offers: list["GbOffer"] | None = None


class GbPrice(BaseModel):
    amount: float
    currencyCode: str


class GbOffer(BaseModel):
    finskyOfferType: int
    listPrice: "GbMicroPrice"
    retailPrice: "GbMicroPrice"
    giftable: bool


class GbMicroPrice(BaseModel):
    amountInMicros: int
    currencyCode: str


class GbAccessInfo(BaseModel):
    country: str
    viewability: str
    embeddable: bool
    publicDomain: bool
    textToSpeechPermission: str
    epub: "GbEpub | None" = None
    pdf: "GbPdf | None" = None
    webReaderLink: str | None = None
    accessViewStatus: str
    quoteSharingAllowed: bool


class GbEpub(BaseModel):
    isAvailable: bool
    acsTokenLink: str | None = None


class GbPdf(BaseModel):
    isAvailable: bool
    acsTokenLink: str | None = None


class GbSearchInfo(BaseModel):
    textSnippet: str

### Tavily
class TavilyResponse(BaseModel):
    query: str
    follow_up_questions: list[str] | None = None
    answer: str | None = None
    images: list["TavilyImage"] = Field(default_factory=list)
    results: list["TavilyResult"]
    response_time: float
    usage: "TavilyUsage"
    request_id: str


class TavilyResult(BaseModel):
    url: str
    title: str
    content: str
    score: float
    raw_content: str | None = None
    id: str


class TavilyImage(BaseModel):
    pass


class TavilyUsage(BaseModel):
    credits: int