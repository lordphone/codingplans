import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

/** One model block inside a tier card (name + QUANT/TPS/TTFT strip) */
interface PlanModelRow {
  id: string;
  name: string;
  quantization: string;
  quantizationColor: 'tertiary' | 'secondary';
  tps: string;
  /** Time to first token (display string, e.g. seconds) */
  ttft: string;
}

interface PlanDetail {
  id: string;
  name: string;
  tierId: string;
  price: string;
  period: string;
  models: PlanModelRow[];
}

@Component({
  selector: 'app-provider',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './provider.component.html'
})
export class ProviderComponent {
  @Input() providerId: string = '';

  providerName = 'Alibaba Cloud';
  lastUpdated = '2024-10-24 14:30:01 UTC';

  plans: PlanDetail[] = [
    {
      id: 'lite',
      name: 'LITE ENTRY',
      tierId: 'ACMS LITE 001',
      price: '$10',
      period: '/ MO',
      models: [
        {
          id: 'kimi-8b',
          name: 'Kimi 8B',
          quantization: 'INT4',
          quantizationColor: 'tertiary',
          tps: '18.5',
          ttft: '0.38s'
        },
        {
          id: 'kimi-2b',
          name: 'Kimi 2B',
          quantization: 'INT8',
          quantizationColor: 'tertiary',
          tps: '44.0',
          ttft: '0.21s'
        }
      ]
    },
    {
      id: 'standard',
      name: 'STANDARD (TEST)',
      tierId: 'ACMS STD 200',
      price: '$25',
      period: '/ MO',
      models: [
        {
          id: 'kimi-8b',
          name: 'Kimi 8B',
          quantization: 'INT8',
          quantizationColor: 'tertiary',
          tps: '52.0',
          ttft: '0.31s'
        },
        {
          id: 'qwen-7b',
          name: 'Qwen 7B',
          quantization: 'INT8',
          quantizationColor: 'tertiary',
          tps: '61.0',
          ttft: '0.29s'
        }
      ]
    },
    {
      id: 'pro',
      name: 'PRO ELITE',
      tierId: 'ACMS PRO 500',
      price: '$50',
      period: '/ MO',
      models: [
        {
          id: 'kimi-8b',
          name: 'Kimi 8B',
          quantization: 'FP16',
          quantizationColor: 'secondary',
          tps: '142.0',
          ttft: '0.24s'
        },
        {
          id: 'kimi-70b',
          name: 'Kimi 70B',
          quantization: 'FP16',
          quantizationColor: 'secondary',
          tps: '38.0',
          ttft: '0.55s'
        }
      ]
    }
  ];
}
