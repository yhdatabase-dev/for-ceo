/**
 * 검토 결과 화면 E2E 스모크 — 리팩토링(reviewShared 공용화) 회귀 방지.
 *
 * 백엔드 없이 sessionStorage 에 검토 결과를 시드해 EC 결과 페이지가
 * 올바르게 렌더되는지 검증한다 (수동 프리뷰 검증을 코드화한 것).
 *
 * 보증 항목
 *  - 좌측 본문 마커(buildMarkerHits)·법령 링크(lawArticleUrl)·메타 칩(parseMetaTags)
 *  - <meta db=...> 원시 태그가 화면에 새지 않음
 *  - 페이지 크래시(uncaught error) 없음 — 백엔드 다운 상태의 폴백 포함
 *  - 모바일(375px) 분기 렌더
 */
import { expect, Page, test } from '@playwright/test';

const EC_ENTRY = {
  caseId: 'e2e-ec',
  status: 'done',
  documentType: 'employment-contract',
  startedAt: 1751000000000,
  doneAt: 1751000100000,
  originalFilename: 'e2e근로계약서.txt',
  ec: {
    phase: 'result',
    extractedText:
      '표준근로계약서. 사업주와 근로자는 다음과 같이 근로계약을 체결한다. 근무 장소: 서울 본사. 업무 내용: 사무 보조. 임금: 월 2,090,000원. 소정근로시간: 주 40시간. 휴일: 주휴일 일요일. 연차유급휴가는 근로기준법에 따른다.',
    businessSize: '5+',
    workerTypes: ['정규직'],
    analysisResult: {
      riskLevel: '중',
      overallStatus: '보완필요',
      overallOpinion: '일부 항목 보완이 필요합니다.',
      finalRecommendations: '임금 구성항목을 명시하세요.',
      results: [
        {
          항목: '임금',
          적용조건: '공통',
          서면명시의무: '필수_서면교부',
          적절성: '부적절',
          판단이유:
            "임금 구성항목·계산방법 누락 <meta db='DB_근로기준법' n='제17조' /> <meta db='DB_임금' n='3.1' />",
          발견내용: '월 2,090,000원',
          법적근거: '근로기준법 제17조',
          개선권고: '임금 구성항목·계산방법·지급방법을 명시',
        },
        {
          항목: '근무 장소',
          적용조건: '공통',
          서면명시의무: '필수',
          적절성: '적절',
          판단이유: '명시됨',
          발견내용: '서울 본사',
          법적근거: '근로기준법 제17조',
          개선권고: '',
        },
        {
          항목: '소정근로시간',
          적용조건: '공통',
          서면명시의무: '필수',
          적절성: '보완필요',
          판단이유: "휴게시간 미기재 <meta db='DB_근로기준법' n='제54조' />",
          발견내용: '주 40시간',
          법적근거: '근로기준법 제54조',
          개선권고: '휴게시간을 명시',
        },
      ],
    },
  },
};


/** 페이지 로드 전에 sessionStorage 시드 + 크래시 수집기 부착. */
async function seedAndCollect(page: Page, entry: { caseId: string }) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  await page.addInitScript(
    ([key, value]) => window.sessionStorage.setItem(key, value),
    [`cgr.review.${entry.caseId}`, JSON.stringify(entry)] as const,
  );
  return errors;
}

test('EC 결과 페이지 — 마커·법령링크·메타칩 렌더 (데스크톱)', async ({ page }) => {
  const errors = await seedAndCollect(page, EC_ENTRY);
  await page.goto('/review/e2e-ec/ec');

  // 종합 판정 카드
  await expect(page.getByText('종합 판정')).toBeVisible();
  // 좌측 본문 마커 (buildMarkerHits) — 부적절·보완필요 2건
  await expect(page.locator('mark')).toHaveCount(2);
  // 법령 meta → 국가법령정보센터 링크 (isLawDb·lawArticleUrl)
  await expect(page.locator("a[href*='law.go.kr']").first()).toBeVisible();
  // 비법령 meta → 주제 칩 (MetaHoverChipsRow)
  await expect(page.locator("[class*='metaHoverChip']").first()).toBeVisible();
  // 원시 <meta db=...> 태그 누출 없음 (parseMetaTags)
  await expect(page.locator('body')).not.toContainText("db='DB_");
  expect(errors).toEqual([]);
});

test('EC 결과 페이지 — 모바일(375px) 분기 렌더', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const errors = await seedAndCollect(page, EC_ENTRY);
  await page.goto('/review/e2e-ec/ec');

  await expect(page.getByText('종합 판정').first()).toBeVisible();
  // 모바일 전용 CTA — 수정본 만들기
  await expect(page.getByText('수정본 만들기')).toBeVisible();
  await expect(page.locator('body')).not.toContainText("db='DB_");
  expect(errors).toEqual([]);
});
