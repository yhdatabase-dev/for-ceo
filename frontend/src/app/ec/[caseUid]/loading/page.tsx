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
