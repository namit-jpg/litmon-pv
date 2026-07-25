from app.services.pubmed.client import parse_efetch_xml

SAMPLE = """<?xml version="1.0"?>
<!DOCTYPE PubmedArticleSet PUBLIC "-//NLM//DTD PubMedArticle, 1st January 2024//EN" "https://dtd.nlm.nih.gov/ncbi/pubmed/out/pubmed_240101.dtd">
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID>12345678</PMID>
   <Article>
    <Journal>
     <Title>Demo Journal</Title>
     <JournalIssue>
      <PubDate><Year>2024</Year><Month>Jun</Month><Day>15</Day></PubDate>
     </JournalIssue>
    </Journal>
    <ArticleTitle>DrugX case report of rash</ArticleTitle>
    <Abstract>
     <AbstractText>We report a patient with rash after DrugX.</AbstractText>
    </Abstract>
    <AuthorList>
     <Author><LastName>Smith</LastName><ForeName>Jane</ForeName></Author>
    </AuthorList>
    <PublicationTypeList>
     <PublicationType>Case Reports</PublicationType>
    </PublicationTypeList>
    <ELocationID EIdType="doi">10.1000/demo</ELocationID>
   </Article>
   <MeshHeadingList>
    <MeshHeading><DescriptorName>Exanthema</DescriptorName></MeshHeading>
   </MeshHeadingList>
  </MedlineCitation>
 </PubmedArticle>
</PubmedArticleSet>
"""


def test_parse_efetch():
    arts = parse_efetch_xml(SAMPLE)
    assert len(arts) == 1
    a = arts[0]
    assert a.pmid == "12345678"
    assert "DrugX" in a.title
    assert a.doi == "10.1000/demo"
    assert a.authors == ["Smith Jane"]
    assert "Exanthema" in a.mesh_terms
