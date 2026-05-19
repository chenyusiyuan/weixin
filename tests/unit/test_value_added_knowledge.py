from pathlib import Path

from fin_copilot.knowledge.value_added import ValueAddedKnowledgeRetriever
from fin_copilot.models.conversation import ConversationState
from fin_copilot.models.response import CopilotResponse
from fin_copilot.routing.domain_classifier import DomainClassifier


ROOT = Path(__file__).resolve().parents[2]


def test_value_added_retriever_matches_text_and_image_blocks():
    retriever = ValueAddedKnowledgeRetriever(ROOT)

    result = retriever.retrieve(
        "还款无忧服务是什么，为什么会产生费用",
        "value_added_service_inquiry",
    )

    assert result is not None
    assert result["status"] == "matched"
    assert result["slots"]["value_added_matched_service_id"] == "debt_consulting_service_fee"
    assert result["knowledge_matches"] == [{
        "domain": "活动",
        "category": "增值服务",
        "service_id": "debt_consulting_service_fee",
        "service_name": "债务咨询顾问服务费/还款无忧",
        "match_status": "matched",
        "suspected_non_company_product": False,
        "matched_aliases": ["还款无忧", "还款无忧服务"],
    }]
    assert "费用类型" in result["prompt_text"]
    assert "图片补充块" in result["prompt_text"]
    assert result["references"]


def test_value_added_retriever_matches_image_heavy_service():
    retriever = ValueAddedKnowledgeRetriever(ROOT)

    result = retriever.retrieve("100元话费券怎么充值", "value_added_service_inquiry")

    assert result is not None
    assert result["status"] == "matched"
    assert result["slots"]["value_added_matched_service_id"] == "phone_credit_coupon"
    assert "19.9买100元话费券" in result["prompt_text"]
    assert "话费充值权益页" in result["prompt_text"]


def test_value_added_retriever_unmatched_non_company_flow():
    retriever = ValueAddedKnowledgeRetriever(ROOT)

    result = retriever.retrieve(
        "我想取消一个赚钱卡，不知道是不是你们的产品",
        "cancel_value_added_service",
    )

    assert result is not None
    assert result["status"] == "unmatched"
    assert result["slots"]["value_added_match_status"] == "unmatched"
    assert result["slots"]["value_added_suspected_non_company_product"] is True
    assert result["knowledge_matches"] == [{
        "domain": "活动",
        "category": "增值服务",
        "service_id": "",
        "service_name": "",
        "match_status": "unmatched",
        "suspected_non_company_product": True,
    }]
    assert "匹配失败/非我司产品处理流程" in result["prompt_text"]
    assert "不要直接承诺取消" in result["prompt_text"]


def test_value_added_terms_route_to_activity_domain():
    classifier = DomainClassifier()
    state = ConversationState(session_id="domain-smoke")

    assert classifier.classify("还款无忧服务是什么", state) == "活动"
    assert classifier.classify("债务咨询顾问服务费为什么会产生", state) == "活动"
    assert classifier.classify("我想取消一个赚钱卡，不知道是不是你们的产品", state) == "活动"


def test_copilot_response_can_expose_knowledge_matches():
    response = CopilotResponse(
        answer="ok",
        knowledge_matches=[{
            "domain": "活动",
            "category": "增值服务",
            "service_id": "debt_consulting_service_fee",
            "service_name": "债务咨询顾问服务费/还款无忧",
            "match_status": "matched",
            "suspected_non_company_product": False,
        }],
    )

    dumped = response.model_dump()
    assert dumped["knowledge_matches"][0]["service_id"] == "debt_consulting_service_fee"
