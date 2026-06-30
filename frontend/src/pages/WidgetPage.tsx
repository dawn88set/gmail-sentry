import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import Widget from '@/components/Widget';
import type { WidgetSize } from '@/lib/widget-sizes';

const SIZES: WidgetSize[] = ['small', 'medium', 'large'];

export default function WidgetPage() {
  const [searchParams] = useSearchParams();
  const raw = (searchParams.get('size') || 'large') as WidgetSize;
  const size: WidgetSize = SIZES.includes(raw) ? raw : 'large';

  // The platform embeds this page in an iframe sized EXACTLY to the widget
  // (small 170×170, medium 360×170, large 360×360). So the host must add NO
  // background, padding, or margin around it, and the widget must cast no
  // shadow — render the bare widget flush. `widget-host` (see index.css) makes
  // the body transparent + zero-margin and removes the widget's shadow so
  // nothing is clipped or offset by the iframe edge.
  useEffect(() => {
    document.body.classList.add('widget-host');
    return () => document.body.classList.remove('widget-host');
  }, []);

  return <Widget size={size} />;
}
