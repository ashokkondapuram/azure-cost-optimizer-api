import { fetchAllOpenFindings } from './findingsUtils';
import { fetchFindingsPage } from '../api/azure';

jest.mock('../api/azure', () => ({
  fetchFindingsPage: jest.fn(),
}));

describe('findingsUtils', () => {
  beforeEach(() => {
    fetchFindingsPage.mockReset();
  });

  it('fetches all open finding pages until exhausted', async () => {
    fetchFindingsPage
      .mockResolvedValueOnce({
        items: [{ id: '1' }, { id: '2' }],
        total: 3,
        has_more: true,
      })
      .mockResolvedValueOnce({
        items: [{ id: '3' }],
        total: 3,
        has_more: false,
      });

    const result = await fetchAllOpenFindings('sub-1');
    expect(result.items).toHaveLength(3);
    expect(result.total).toBe(3);
    expect(fetchFindingsPage).toHaveBeenCalledTimes(2);
  });
});
