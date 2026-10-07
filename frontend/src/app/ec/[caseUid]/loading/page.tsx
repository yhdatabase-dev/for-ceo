/**
 * << 개정이력(Modification Information) >>
 * 수정일          수정자      수정 내용
 * ----------      ------      ---------------------------
 * 2026.05.28      kimzion77   최초 생성
 * 2026.10.01      이시영      버전 정렬 (Python 3.14.7·Node 24.21.0·Next 16.3.5)
 * 2026.10.07      이시영      화면 경로 /cgr·features 구조 이동, sync API 삭제, 업로드 원본 미저장
 * 2026.10.07      이시영      검토번호 서버 발급, 변경 사유 주석 추가
 *
 * Author: kimzion77
 * Since: 2026.05.28
 */
// 개발표준정의서 API 엔드포인트(화면 경로): 진행 화면을 도메인 ec 아래로 — /cgr/ec/[caseUid]/loading (기존: /review/[id]/loading 공용)
import LoadingScreen from '@/components/review/LoadingScreen';

/**
 * 검토 진행 중 페이지.
 *
 * 시안 `screens-loading.jsx` 이식. 진행률 100% 도달 시 결과 페이지로 자동 이동하는
 * 부분은 결과 화면 구현 후 LoadingScreen 내부에 `router.replace` 로 추가한다.
 */
export default async function ReviewLoadingPage(
  props: {
    params: Promise<{ caseUid: string }>;
  }
) {
  const params = await props.params;
  return <LoadingScreen reviewId={params.caseUid} />;
}
