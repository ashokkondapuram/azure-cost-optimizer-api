import useMediaQuery from './useMediaQuery';

/** Mobile breakpoint — cards below, table at md and up. */
export const MOBILE_MAX_WIDTH_PX = 767;
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_MAX_WIDTH_PX}px)`;

export default function useResponsiveView() {
  const isMobile = useMediaQuery(MOBILE_MEDIA_QUERY);
  return { isMobile, isDesktop: !isMobile };
}
