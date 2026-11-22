from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, Json, StrictInt, model_validator


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


class GraphCoverageItem(BaseModel):
    outcome_id: str = Field(
        default="",
        description="Transient identifier of the planned outcome this coverage "
        "item implements; empty only for legacy single-stage graph responses.",
    )
    outcome: str = Field(
        min_length=1,
        description="A necessary learner outcome within the requested graph scope.",
    )
    node_ids: list[StrictInt] = Field(
        min_length=1,
        description="Graph-local leaf node identifiers that teach this outcome.",
    )


class GraphBlueprintOutcome(BaseModel):
    id: str = Field(
        pattern=r"^outcome_[1-9]\d*$",
        description="Stable blueprint-local ID in the form outcome_N.",
    )
    outcome: str = Field(
        min_length=1,
        description="One atomic, observable in-scope outcome covering a single "
        "concept, skill, or bounded procedure for one focused lesson.",
    )
    evidence: str = Field(
        min_length=1,
        description="A concise assessment or performance that demonstrates "
        "the learner achieved this outcome.",
    )
    prerequisite_ids: list[str] = Field(
        default_factory=list,
        description="Blueprint outcome IDs that are essential prerequisites.",
    )


class ManipulateGraphPlanResponse(BaseModel):
    scope: str = Field(
        min_length=1,
        description="Bounded target performance and scope boundaries for the "
        "learning graph.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicitly labeled assumptions that affect graph scope.",
    )
    prior_knowledge: list[str] = Field(
        default_factory=list,
        description="Prerequisite knowledge explicitly stated by the learner.",
    )
    outcomes: list[GraphBlueprintOutcome] = Field(
        min_length=1,
        description="Complete set of necessary in-scope outcomes, with evidence "
        "and prerequisite outcome IDs; this planning response contains no graph.",
    )

    @model_validator(mode="after")
    def validate_outcome_dependencies(self) -> ManipulateGraphPlanResponse:
        if not self.scope.strip():
            raise ValueError("Blueprint scope must not be blank.")
        outcomes_by_id = {outcome.id: outcome for outcome in self.outcomes}
        if len(outcomes_by_id) != len(self.outcomes):
            raise ValueError("Blueprint outcome IDs must be unique.")

        normalized_outcomes: set[str] = set()
        for outcome in self.outcomes:
            if not outcome.outcome.strip() or not outcome.evidence.strip():
                raise ValueError(
                    f"Outcome '{outcome.id}' requires outcome text and evidence."
                )
            normalized = " ".join(outcome.outcome.casefold().split())
            if normalized in normalized_outcomes:
                raise ValueError("Blueprint outcome statements must be unique.")
            normalized_outcomes.add(normalized)
            if len(set(outcome.prerequisite_ids)) != len(
                outcome.prerequisite_ids
            ):
                raise ValueError(
                    f"Outcome '{outcome.id}' repeats a prerequisite ID."
                )
            for prerequisite_id in outcome.prerequisite_ids:
                if prerequisite_id not in outcomes_by_id:
                    raise ValueError(
                        f"Outcome '{outcome.id}' references unknown prerequisite "
                        f"'{prerequisite_id}'."
                    )
                if prerequisite_id == outcome.id:
                    raise ValueError(
                        f"Outcome '{outcome.id}' cannot depend on itself."
                    )

        indegree = {outcome_id: 0 for outcome_id in outcomes_by_id}
        dependents: dict[str, list[str]] = {}
        for outcome in self.outcomes:
            for prerequisite_id in outcome.prerequisite_ids:
                indegree[outcome.id] += 1
                dependents.setdefault(prerequisite_id, []).append(outcome.id)

        ready = [
            outcome_id
            for outcome_id, dependency_count in indegree.items()
            if dependency_count == 0
        ]
        visited_count = 0
        while ready:
            outcome_id = ready.pop()
            visited_count += 1
            for dependent_id in dependents.get(outcome_id, []):
                indegree[dependent_id] -= 1
                if indegree[dependent_id] == 0:
                    ready.append(dependent_id)
        if visited_count != len(outcomes_by_id):
            raise ValueError("Blueprint outcome dependencies contain a cycle.")
        return self


class ManipulateGraphResponse(BaseModel):
    plan: str = Field(
        default="",
        description="Brief target outcome, scope, assumptions, and starting point "
        "for a newly created graph; discarded and not persisted.",
    )
    coverage: list[GraphCoverageItem] = Field(
        default_factory=list,
        description="Coverage ledger mapping every necessary in-scope learner "
        "outcome to one or more leaf node IDs; transient and not persisted.",
    )
    graph_title: str = Field(description="Human-readable title of the graph.")
  # graph_description:str 
    nodes: list[GraphNode] = Field(
        description="Graph nodes; each node's type describes its place in the "
        "AREA/TOPIC/CONCEPT/SUBCONCEPT hierarchy.",
    )
    edges: list[GraphEdge] = Field(
        description="Relations between nodes; edge type describes containment "
        "or prerequisite semantics, not the node's category.",
    )
    
class GraphNode(BaseModel):
    node_id: int = Field(description="Unique graph-local node identifier.")
    title: str = Field(
        description="Specific name of one concept or bounded skill; do not use "
        "a broad subject or combine independently teachable ideas.",
    )
    description: str = Field(
        default="",
        description="Concise, specific learning objective for one leaf, "
        "describing an observable outcome; a short scope summary for a container.",
    )
    type: GraphType = Field(
        description="Structural node category: AREA, TOPIC, CONCEPT, or SUBCONCEPT.",
    )
    level: Literal["foundation", "core", "advanced"] = Field(
        default="core",
        description="Transient learning level used to validate graph generation; "
        "not persisted by the app.",
    )

class GenerateNodeDescription(BaseModel):
    description: str

class GraphEdge(BaseModel):
    source_node: int = Field(description="Graph-local identifier of the source node.")
    target_node: int = Field(description="Graph-local identifier of the target node.")
    type: EdgeType = Field(
        description="Relation kind: SUBTOPIC represents containment; PREREQUISITE "
        "means the source should be learned before the target.",
    )
    weight: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Prerequisite importance: 1.0 is essential and 0.5 is helpful "
        "but optional. Stored in the existing graph_edge.weight column.",
    )
    

GraphPatchId = Annotated[StrictInt, Field(gt=0)]
GraphPatchNodeReference = (
    GraphPatchId
    | Annotated[str, Field(pattern=r"^new_[1-9]\d*$")]
)


class GraphNodeRename(BaseModel):
    id: GraphPatchId = Field(description="Existing graph-local node identifier.")
    title: str = Field(min_length=1, description="Replacement node title.")


class GraphNodeAddition(BaseModel):
    id: str = Field(
        pattern=r"^new_[1-9]\d*$",
        description="Temporary identifier in the form new_N.",
    )
    title: str = Field(min_length=1, description="Title of the new node.")
    type: GraphType = Field(
        default=GraphType.CONCEPT,
        description="Structural node category of the new node.",
    )


class GraphEdgeAddition(BaseModel):
    source_node: GraphPatchNodeReference = Field(
        description="Existing positive node ID or a new_N ID declared in add_nodes."
    )
    target_node: GraphPatchNodeReference = Field(
        description="Existing positive node ID or a new_N ID declared in add_nodes."
    )
    type: EdgeType = Field(description="Relation kind for the new edge.")
    weight: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Importance of a new prerequisite edge; defaults to essential.",
    )


class ManipulateGraphPatchResponse(BaseModel):
    delete_nodes: list[GraphPatchId] = Field(
        default_factory=list,
        description="Existing node identifiers to delete.",
    )
    rename_nodes: list[GraphNodeRename] = Field(
        default_factory=list,
        description="Existing nodes to rename.",
    )
    add_nodes: list[GraphNodeAddition] = Field(
        default_factory=list,
        description="New nodes to add using temporary new_N identifiers.",
    )
    delete_edges: list[GraphPatchId] = Field(
        default_factory=list,
        description="Existing edge identifiers to delete.",
    )
    add_edges: list[GraphEdgeAddition] = Field(
        default_factory=list,
        description="Edges to add using existing or declared new_N node IDs.",
    )


##################
### EvaluateEssayQuestionResponse
##################
class EvaluateEssayQuestionResponse(BaseModel):
    feedback: str
    conceptualRequisites: ConceptualRequisites
    textCoerence: TextCoerence
    
class EvaluateFeynmanResponse(BaseModel):
    feedback: str
    conceptualRequisites: ConceptualRequisites
    textCoerence: TextCoerence
    feynmanRequisites: FeynmanRequisites


class FeynmanRequisites(BaseModel):
    explanation_acessibility: int = Field(ge=0, le=100)
    logic_progression: int = Field(ge=0, le=100)
    gaps: int = Field(ge=0, le=100)
    

class ConceptualRequisites(BaseModel): ## TODO Verificar inglês
    fidelity_to_question: int = Field(ge=0, le=100)
    teoric_precision: int = Field(ge=0, le=100)
    response_deep: int = Field(ge=0, le=100)
    
class TextCoerence(BaseModel):
    coerence: int = Field(ge=0, le=100)
    argument_struct: int = Field(ge=0, le=100)
    argument_clarity: int = Field(ge=0, le=100)
    
###################
### ManipulateNodeResponse
###################
class ManipulateNodeResponse(BaseModel):
    changed_nodes: list[GraphNodeEdit]
    changed_edges: list[GraphEdgeEdit]
    
class GraphNodeEdit(BaseModel):
    node_id: Optional[int | None] = None
    title: Optional[str | None] = None
  # description:str
    type: GraphType
class GraphEdgeEdit(BaseModel):
    source_node: Optional[int | None] = None
    target_node: Optional[int | None] = None
    type: Optional[EdgeType | None] = None

###################
### CreateStudySessionResponse
###################
class CreateStudySessionResponse(BaseModel):
    alternative_questions_ids: Optional[list[int] | None] = None
    dissertative_questions_ids: Optional[list[int] | None] = None
    target: str


###################
### Flashcards
###################
class CreateFlashcard(BaseModel):
    title: str
    statement: str
    target_skill: str | None = None


class CreateFlashcardsResponse(BaseModel):
    flashcards: list[CreateFlashcard]


class CreateFlashcardGroup(BaseModel):
    name: str
    description: str | None = None


class ManipulateFlashcardGroup(BaseModel):
    name: str | None = None
    description: str | None = None


class StudyManagerResponse(BaseModel):
    target_duration_min: int = Field(gt=0)
    interleaving_enabled: bool = False
    diagnostic_focus: bool = False
    total_activities: int = Field(default=0, ge=0)


class StudyAssistantAction(BaseModel):
    type: Literal["create_graph", "create_flashcards", "create_exercise", "navigate"]
    title: str
    prompt: str = ""
    destination: Literal[
        "home", "graphs", "flashcards", "notes", "study_sessions"
    ] | None = None
    exercise_type: Literal["multiple_choice", "open_ended"] | None = None
    graph_id: str | None = None
    node_id: str | None = None


class StudyAssistentResponse(BaseModel):
    feedback: str
    next_activity: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    actions: list[StudyAssistantAction] = Field(default_factory=list, max_length=3)

###################
### CreateEssayQuestionResponse
###################
class CreateEssayQuestionResponse(BaseModel):
    title: str
    statement: str
    reference_correct_answer: str
    
###################
### CreateFeynmanResponse
###################
class CreateFeynmanResponse(BaseModel):
    title: str
    statement: str
    reference_correct_answer: str

###################
### CreateMultipleChoiceQuestionResponse
###################
class CreateMultipleChoiceQuestionResponse(BaseModel):
    title: str
    statement: str
    choices: list[Choise] = Field(min_length=4, max_length=4)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_choices_key(cls, value):
        if isinstance(value, dict) and "choices" not in value and "choises" in value:
            value = {**value, "choices": value["choises"]}
        return value

    @model_validator(mode="after")
    def require_one_correct_choice(self):
        if sum(choice.is_correct for choice in self.choices) != 1:
            raise ValueError("A questão deve ter exatamente uma alternativa correta.")
        return self


class Choise(BaseModel):
    is_correct: bool
    statement: str
    explanation: str
    weight: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_weight_key(cls, value):
        if isinstance(value, dict) and "weight" not in value and "weigth" in value:
            value = {**value, "weight": value["weigth"]}
        return value


###################
### EvaluateMultipleChoiceQuestionResponse
###################
class EvaluateMultipleChoiceQuestionResponse(BaseModel):
    explanation: str
    tips: str

###################
### External resources query generation
###################
class ExternalResourcesOut(BaseModel):
    papers: list[S2SearchResult]
    search_results: TavilyResponse
    yt_videos: list[YtSearchResult]
    books: list[GbBook]

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

from pydantic import BaseModel, Field


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
    s2FieldsOfStudy: list["S2FieldOfStudy"] = Field(default_factory=list)

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
    
